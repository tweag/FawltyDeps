{
  pkgs ? import (builtins.fetchGit {
    url = "https://github.com/NixOS/nixpkgs/";
    ref = "nixos-22.11";
  }) {}
}:

pkgs.mkShell {
  name = "fawltydeps-env";
  buildInputs = with pkgs; [
    python37
    python38
    python39
    (python310.withPackages (pypkgs: with pypkgs; [
      poetry
    ]))
    python311
  ];
  shellHook = ''
    # This is needed to keep python3.7 working while in the same nix-shell
    # as a later python (see https://github.com/NixOS/nixpkgs/issues/88711
    # for more details):
    unset _PYTHON_HOST_PLATFORM
    unset _PYTHON_SYSCONFIGDATA_NAME

    poetry env use "${pkgs.python310}/bin/python"
    poetry install --sync --with=dev
    source "$(poetry env info --path)/bin/activate"
  '';
}
