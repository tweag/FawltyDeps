{
  pkgsWithOldPythons ? import (builtins.fetchTarball {
    # Branch: nixos-22.11
    url = "https://github.com/NixOS/nixpkgs/archive/96e18717904dfedcd884541e5a92bf9ff632cf39.tar.gz";
    sha256 = "0zw1851mia86xqxdf8jgy1c6fm5lqw4rncv7v2lwxar3vhpn6c78";
  }) {},
  old_pythons_overlay ? self: super: {
    python37 = pkgsWithOldPythons.python37;
    python38 = pkgsWithOldPythons.python38;
  },
  pkgs ? import (builtins.fetchTarball {
    # Branch: nixos-unstable
    url = "https://github.com/NixOS/nixpkgs/archive/c75037bbf9093a2acb617804ee46320d6d1fea5a.tar.gz";
    sha256 = "1hs4rfylv0f1sbyhs1hf4f7jsq4np498fbcs5xjlmrkwhx4lpgmc";
  }) { overlays = [ old_pythons_overlay ]; }
}:
pkgs.mkShell {
  name = "fawltydeps-env";
  buildInputs = with pkgs; [
    python37
    python38
    python39
    python310
    python311
    python312
    poetry

    # Allow installation of binary wheels by (a) providing manylinux2014
    # support, and (b) patching binaries installed into the Poetry virtualenv.
    autoPatchelfHook
    pythonManylinuxPackages.manylinux2014
  ];
  shellHook = ''
    # This is needed to keep python3.7 working while in the same nix-shell
    # as a later python (see https://github.com/NixOS/nixpkgs/issues/88711
    # for more details):
    unset _PYTHON_HOST_PLATFORM
    unset _PYTHON_SYSCONFIGDATA_NAME

    poetry env use "${pkgs.python311}/bin/python"
    poetry install --sync --with=dev
    # Patch binaries in the Poetry virtualenv to link against Nix deps
    autoPatchelf "$(poetry env info --path)"
    source "$(poetry env info --path)/bin/activate"
  '';
}
