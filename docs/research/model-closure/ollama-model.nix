# One fixed-output derivation per registry blob, then a pure assembly into the directory
# layout Ollama reads as OLLAMA_MODELS. The pin is the registry manifest, kept as a text file:
# digests are the sha256 of each file, so no hash needs a download to discover it.
{ lib, fetchurl, runCommand, jq, coreutils }:
{ repo                                 # "library/smollm"
, tag                                  # "135m"
, manifestFile                         # the registry manifest, verbatim
, parameters ? null                    # attrset: replaces the params layer
, systemPrompt ? null                  # string: adds or replaces the system layer
, registry ? "registry.ollama.ai"
, canFetch ? true                      # false: a builder that refuses, no URL, cannot reach a network
}:
let
  manifest = lib.importJSON manifestFile;
  hexOf = digest: lib.removePrefix "sha256:" digest;
  # Named by digest alone: two tags sharing a blob share a store path, and a blob already
  # on disk can be added with this name and is never fetched. fetchurl and requireFile
  # give the same store path, because a fixed output is addressed by name and hash only.
  fetchBlob = layer:
    let
      name = "ollama-blob-${hexOf layer.digest}";
      sha256 = hexOf layer.digest;
    in
    if canFetch then
      fetchurl { inherit name sha256; url = "https://${registry}/v2/${repo}/blobs/${layer.digest}"; }
    else
      # A fixed output with a builder that can only refuse: same store path as fetchurl,
      # and no URL for an Install to reach. (requireFile would mark Apache weights unfree.)
      derivation {
        inherit name;
        system = "aarch64-darwin";
        builder = "/bin/sh";
        args = [ "-c" "echo 'Model blob ${name} (${toString layer.size} bytes) is not on this computer. An Install does not download models: copy it from the model USB.' >&2; exit 1" ];
        outputHashMode = "flat";
        outputHashAlgo = "sha256";
        outputHash = sha256;
      };
  blobs = map (l: { inherit (l) digest; path = fetchBlob l; }) (manifest.layers ++ [ manifest.config ]);
  link = b: "ln -s ${b.path} $blobs/sha256-${hexOf b.digest}";
  edit = lib.optionalString (parameters != null || systemPrompt != null) ''
    layer() { # mediaType file: put file in as a blob, swap it into the manifest
      hex=$(sha256sum "$2" | cut -d' ' -f1); size=$(wc -c < "$2" | tr -d ' ')
      cp "$2" "$blobs/sha256-$hex"
      jq --arg t "$1" --arg d "sha256:$hex" --argjson s "$size" \
        '.layers = ([.layers[] | select(.mediaType != $t)] + [{mediaType:$t,digest:$d,size:$s}])' \
        manifest.json > m.tmp && mv -f m.tmp manifest.json
    }
    ${lib.optionalString (parameters != null) ''layer application/vnd.ollama.image.params ${builtins.toFile "params.json" (builtins.toJSON parameters)}''}
    ${lib.optionalString (systemPrompt != null) ''layer application/vnd.ollama.image.system ${builtins.toFile "system.txt" systemPrompt}''}
  '';
in
runCommand "ollama-model-${baseNameOf repo}-${tag}" {
  nativeBuildInputs = [ jq coreutils ];
  allowSubstitutes = false;
  preferLocalBuild = true;
  passthru = { inherit blobs manifest; };
} ''
  blobs=$out/share/ollama/models/blobs
  mdir=$out/share/ollama/models/manifests/${registry}/${repo}
  # manifests-v2: Ollama 0.40 runs MkdirAll on it for every lookup, which fails on a
  # read-only store unless it already exists.
  mkdir -p $blobs $mdir $out/share/ollama/models/manifests-v2
  ${lib.concatMapStringsSep "\n" link blobs}
  cp ${manifestFile} manifest.json && chmod u+w manifest.json
  ${edit}
  cp manifest.json $mdir/${tag}
''
