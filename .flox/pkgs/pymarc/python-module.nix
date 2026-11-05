{
  lib,
  buildPythonPackage,
  fetchFromGitLab,
  hatchling,
  pytestCheckHook,
}:

buildPythonPackage rec {
  pname = "pymarc";
  version = "5.4.0";
  pyproject = true;

  src = fetchFromGitLab {
    owner = "pymarc";
    repo = "pymarc";
    tag = "v${version}";
    hash = "sha256-SLJ9QgUqyOUsmk8bOI5Hcvc3W4VLB5/zWYZUokeTniM=";
  };

  build-system = [ hatchling ];

  nativeCheckInputs = [ pytestCheckHook ];

  pythonImportsCheck = [ "pymarc" ];

  meta = {
    description = "Read, write and modify MARC bibliographic data";
    homepage = "https://gitlab.com/pymarc/pymarc";
    changelog = "https://gitlab.com/pymarc/pymarc/-/releases/v${version}";
    license = lib.licenses.bsd2;
    maintainers = [ ]; # upstream: with lib.maintainers; [ imkarrer ]
  };
}
