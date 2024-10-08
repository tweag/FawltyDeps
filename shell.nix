{
  pkgsWithOldPythons ? import (builtins.fetchTarball {
    # Branch: nixos-22.11
    url = "https://github.com/NixOS/nixpkgs/archive/96e18717904dfedcd884541e5a92bf9ff632cf39.tar.gz";
    sha256 = "0zw1851mia86xqxdf8jgy1c6fm5lqw4rncv7v2lwxar3vhpn6c78";
  }) {},
  old_pythons_overlay ? self: super: {
    python38 = pkgsWithOldPythons.python38;
  },
  pkgs ? import (builtins.fetchTarball {
    # Branch: nixos-unstable
    url = "https://github.com/NixOS/nixpkgs/archive/62939616bcc4da119f15eed184b124a9383fcf56.tar.gz";
    sha256 = "1nl40n5bbnzwyx1074g38py638s55d2bsn04ynlz9ix1r5f0nv6x";
  }) { overlays = [ old_pythons_overlay ]; }
}:
pkgs.mkShell {
  name = "fawltydeps-env";
  buildInputs = with pkgs; [
    python38
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
    poetry env use "${pkgs.python312}/bin/python"
    poetry install --sync --with=dev
    # Patch binaries in the Poetry virtualenv to link against Nix deps
    autoPatchelf "$(poetry env info --path)"
    source "$(poetry env info --path)/bin/activate"
  '';
}
