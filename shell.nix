{
  pkgs ? import (builtins.fetchGit {
    url = "https://github.com/NixOS/nixpkgs/";
    ref = "nixos-22.11";
  }) {}
}:

pkgs.mkShell {
  name = "fawltydeps-env";
  buildInputs = with pkgs; [
    (python310.withPackages (pypkgs: with pypkgs; [
      poetry
    ]))
  ];
  shellHook = ''
    poetry env use "$(which python)"
    poetry install
    source "$(poetry env info --path)/bin/activate"
  '';
}
