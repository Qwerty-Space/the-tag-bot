{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  name = "tagbot-shell";
  buildInputs = [
    (pkgs.python39.withPackages (ps: with ps; [
      (callPackage ./nix/telethon.nix {})
      (callPackage ./nix/buildpg.nix {})
      asyncpg cachetools
    ]))
  ];
}