#!/usr/bin/env python3
"""TCP Over SSL Tunnel - Main entry point."""

import asyncio
import signal
import sys
from typing import Optional

from config import Config, ConfigurationError, load_config, parse_args
from logger import get_logger, setup_logger
from tunnel import Tunnel
from utils import http_proxy_process, keep_ssh_alive

logger = get_logger()


async def main() -> int:
    """
    Main async entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    setup_logger(
        verbose=args.verbose,
        quiet=args.quiet,
    )

    try:
        config = load_config(args.config)
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    if config.logging.file:
        setup_logger(
            verbose=args.verbose,
            quiet=args.quiet,
            log_file=config.logging.file,
        )

    logger.info("TCP Over SSL Tunnel starting...")
    logger.info(f"Config loaded from: {args.config}")

    stop_event = asyncio.Event()
    connection_semaphore = asyncio.Semaphore(config.settings.max_connections)

    http_proxy_proc = None

    def signal_handler(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig)

    try:
        tunnel = Tunnel(config, stop_event, connection_semaphore)

        tunnel_task = asyncio.create_task(
            tunnel.start(),
            name="tunnel",
        )

        # Wait for tunnel to be ready before starting SSH
        await tunnel.ready_event.wait()
        logger.info("Tunnel ready, starting SSH keepalive...")

        ssh_task = asyncio.create_task(
            keep_ssh_alive(config, stop_event, connection_semaphore),
            name="ssh_keepalive",
        )

        if config.http_proxy.enable:
            http_proxy_proc = http_proxy_process(config)

        await asyncio.gather(ssh_task, tunnel_task, return_exceptions=True)

    except asyncio.CancelledError:
        logger.info("Tasks cancelled")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        logger.info("Cleaning up...")
        stop_event.set()

        if http_proxy_proc:
            http_proxy_proc.terminate()
            try:
                http_proxy_proc.wait(timeout=5)
            except Exception:
                http_proxy_proc.kill()

        logger.info("Cleanup complete. Exiting.")

    return 0


def run() -> None:
    """Entry point wrapper."""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    run()
