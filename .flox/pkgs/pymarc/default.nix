# Until nixpkgs has python3Packages.pymarc. python-module.nix is the file proposed upstream;
# when the catalog has it, install python313Packages.pymarc and delete this directory.
{ python313Packages }: python313Packages.callPackage ./python-module.nix { }
