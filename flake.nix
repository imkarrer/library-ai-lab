# The agent stack for this repo (agent-stacks.org): Claude Code with the skills an agent
# here needs, the same on every machine. From the repo root:
#   nix run
# The Library Assistant itself installs with flox (.flox/), not with this flake.
{
  description = "Claude Code with this repo's agent plugins, as an agent stack";

  inputs.agent-pkgs.url = "github:agent-stacks/agent-pkgs";
  inputs.nixpkgs.follows = "agent-pkgs/nixpkgs";
  # bead-loop's skills for writing beads the loop lands (breakdown, delegate, beads,
  # bead-workflow), from its own flake rather than the public agent-pkgs set.
  inputs.bead-loop.url = "github:imkarrer/bead-loop";
  inputs.bead-loop.inputs.agent-pkgs.follows = "agent-pkgs";
  inputs.bead-loop.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { self, nixpkgs, agent-pkgs, bead-loop }:
    let
      systems = [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in {
      packages = forAllSystems (system: rec {
        agent = agent-pkgs.lib.${system}.mkAgentStack {
          name = "library-ai-lab";
          harness = agent-pkgs.packages.${system}.claude-code;
          plugins = [ bead-loop.packages.${system}.agent-plugin-bead-loop ];
        };
        default = agent;
      });
    };
}
