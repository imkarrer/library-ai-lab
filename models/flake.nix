{
  # Both demo models as pinned Nix inputs, until agent-stacks publishes model packages
  # (lib-552). docs/research/models-in-the-closure.md has the design and what was tested.
  description = "The Library Assistant's local models, pinned by digest";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/31ecbaca1bdefa45dffc409f0250bd8039ea0010";
  outputs = { self, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.aarch64-darwin;
      ollamaModels = pkgs.callPackage ./ollama-model.nix { };
      models = [
        { repo = "library/gpt-oss"; tag = "20b"; manifestFile = ./pins/gpt-oss-20b.json; }
        { repo = "library/qwen3.5"; tag = "4b"; manifestFile = ./pins/qwen3.5-4b.json; }
      ];
    in {
      packages.aarch64-darwin = {
        # What the flox environment installs: never fetches (ADR-0006).
        default = ollamaModels { name = "library-models"; inherit models; };
        # The one setup fetch, ./stack fetch-models: the same store paths, downloaded.
        online = ollamaModels { name = "library-models"; inherit models; canFetch = true; };
      };
    };
}
