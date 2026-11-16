# One fixed-output derivation per registry blob, then a pure assembly into the directory
# layout Ollama reads as OLLAMA_MODELS. Each pin is a registry manifest, kept verbatim as a
# text file: digests are the sha256 of each file, so no hash needs a download to discover it.
{ lib, fetchurl, runCommand }:
{ name
, models                               # [ { repo = "library/qwen3.5"; tag = "4b"; manifestFile = ./pins/qwen3.5-4b.json; } ]
, registry ? "registry.ollama.ai"
, canFetch ? false                     # true only for the one setup fetch (ADR-0006)
}:
let
  hexOf = digest: lib.removePrefix "sha256:" digest;
  # Named by digest alone: two tags sharing a blob share a store path, and a blob already
  # on disk can be added under this name and is never fetched. The fetching and the
  # refusing derivation give the same store path, because a fixed output is addressed by
  # name and hash only, so the Install's sealed assembly finds what setup fetched.
  fetchBlob = repo: layer:
    let
      name = "ollama-blob-${hexOf layer.digest}";
      sha256 = hexOf layer.digest;
    in
    if canFetch then
      fetchurl { inherit name sha256; url = "https://${registry}/v2/${repo}/blobs/${layer.digest}"; }
    else
      # A builder that can only refuse, with no URL: activating an Install never reaches a
      # network for a model. (requireFile would mark Apache weights unfree.)
      derivation {
        inherit name;
        system = "aarch64-darwin";
        builder = "/bin/sh";
        args = [ "-c" "echo 'Model file ${name} (${toString layer.size} bytes) is not on this computer. Run ./stack fetch-models once, online.' >&2; exit 1" ];
        outputHashMode = "flat";
        outputHashAlgo = "sha256";
        outputHash = sha256;
      };
  blobsOf = m:
    let manifest = lib.importJSON m.manifestFile;
    in map (l: { inherit (l) digest; path = fetchBlob m.repo l; }) (manifest.layers ++ [ manifest.config ]);
  blobs = lib.unique (lib.concatMap blobsOf models);
  link = b: "ln -sf ${b.path} $blobs/sha256-${hexOf b.digest}";
  manifest = m: ''
    mkdir -p $models/manifests/${registry}/${m.repo}
    cp ${m.manifestFile} $models/manifests/${registry}/${m.repo}/${m.tag}
  '';
in
runCommand name {
  allowSubstitutes = false;
  preferLocalBuild = true;
  passthru = { inherit blobs; };
} ''
  models=$out/share/ollama/models
  blobs=$models/blobs
  # manifests-v2: Ollama 0.40 runs MkdirAll on it for every lookup, which fails on a
  # read-only store unless it already exists.
  mkdir -p $blobs $models/manifests-v2
  ${lib.concatMapStringsSep "\n" link blobs}
  ${lib.concatMapStringsSep "\n" manifest models}
''
