{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  name = "tagbot-shell";
  buildInputs = [
    (pkgs.python39.withPackages (ps: with ps; [
      (callPackage ./telethon.nix {})
      (callPackage ./buildpg.nix {})
      asyncpg cachetools
    ]))
  ];
}