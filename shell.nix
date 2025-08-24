let
  pkgs = import <nixpkgs> {};
in pkgs.mkShell {
  buildInputs = [
    pkgs.python313
    pkgs.python313.pkgs.pproxy
  ];
  shellHook = ''
    export http_proxy=
    export https_proxy=
    export rsync_proxy=
    export all_proxy=
    export ftp_proxy=
  '';
}
