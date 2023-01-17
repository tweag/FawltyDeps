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
    poetry env use "${pkgs.python310}/bin/python"
    poetry install --sync --with=dev
    source "$(poetry env info --path)/bin/activate"
  '';
}
