{
  pkgs ? import (builtins.fetchTarball {
    # Branch: nixos-unstable
    url = "https://github.com/NixOS/nixpkgs/archive/0196c0175e9191c474c26ab5548db27ef5d34b05.tar.gz";
    sha256 = "sha256-WGaHVAjcrv+Cun7zPlI41SerRtfknGQap281+AakSAw=";
  }) {}
}:
pkgs.mkShell {
  name = "fawltydeps-env";
  buildInputs = with pkgs; [
    python39
    python310
    python311
    python312
    python313
    poetry

    # Allow installation of binary wheels by (a) providing manylinux2014
    # support, and (b) patching binaries installed into the Poetry virtualenv.
    autoPatchelfHook
    pythonManylinuxPackages.manylinux2014
  ];
  shellHook = ''
    poetry env use "${pkgs.python313}/bin/python"
    poetry sync --with=dev
    # Patch binaries in the Poetry virtualenv to link against Nix deps
    autoPatchelf "$(poetry env info --path)"
    source "$(poetry env info --path)/bin/activate"
  '';
}
