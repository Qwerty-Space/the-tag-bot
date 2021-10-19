{ lib, buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "buildpg";
  version = "0.3";

  src = fetchPypi {
    inherit version pname;
    sha256 = "0h6c53674l45ysq6x2v3bjb5fykli62rwia74k83vg3dvvvwl5qy";
  };

  doCheck = false;
}
