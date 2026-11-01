{
  description = "Model weights as pinned Nix inputs (prototype)";
  # The same nixpkgs rev flox's ollama-0.40.6 resolves from.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/31ecbaca1bdefa45dffc409f0250bd8039ea0010";
  outputs = { self, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.aarch64-darwin;
      ollamaModel = pkgs.callPackage ./ollama-model.nix { };
      base = { repo = "library/smollm"; tag = "135m"; manifestFile = ./pins/smollm-135m.json; };
    in {
      packages.aarch64-darwin = {
        default = ollamaModel base;
        secondTag = ollamaModel (base // { tag = "135m-b"; });
        gpt-oss-20b = ollamaModel { repo = "library/gpt-oss"; tag = "20b"; manifestFile = ./pins/gpt-oss-20b.json; };
        qwen35-4b = ollamaModel { repo = "library/qwen3.5"; tag = "4b"; manifestFile = ./pins/qwen3.5-4b.json; };
        sealed = ollamaModel (base // { canFetch = false; });
        behaviour = ollamaModel (base // {
          parameters = { temperature = 0; seed = 42; num_ctx = 2048; stop = [ "<|im_start|>" "<|im_end|>" ]; };
          systemPrompt = "You are a helpful librarian.";
        });
      };
    };
}
