{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  name = "tagbot-shell";
  buildInputs = [
    (pkgs.python39.withPackages (ps: with ps; [
      (callPackage ./nix/telethon.nix {})
      elasticsearch aiohttp elasticsearch-dsl
      cachetools boltons regex emoji
    ]))
  ];
}