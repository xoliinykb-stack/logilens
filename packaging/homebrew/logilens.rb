# Homebrew formula for logilens. It lives in the tap repository xoliinykb-stack/homebrew-tap as
# Formula/logilens.rb, so users can run `brew install xoliinykb-stack/tap/logilens`.
#
# Releasing a new version:
#   1. bump __version__ in src/logilens/__init__.py, then `make release` (tests, builds dist/, prints sha256)
#   2. tag and publish: git tag -a vX.Y.Z -m "logilens X.Y.Z" && git push origin vX.Y.Z
#      gh release create vX.Y.Z dist/* --generate-notes
#   3. copy this file into the tap, set `url` and `sha256` below to the new sdist, commit and push the tap
#   4. check: brew update && brew upgrade logilens && brew test logilens
class Logilens < Formula
  include Language::Python::Virtualenv

  desc "Terminal analyzer for Logisim circuits: lint, K-maps, minimization, FSMs"
  homepage "https://github.com/xoliinykb-stack/logilens"
  url "https://github.com/xoliinykb-stack/logilens/releases/download/v0.1.0/logilens-0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "GPL-3.0-or-later"

  # numpy and scipy come from the Homebrew formulae (built for python@3.13 and python@3.14 only),
  # so the virtualenv must use one of those Pythons and see the system site-packages.
  depends_on "numpy"
  depends_on "openjdk"
  depends_on "python@3.14"
  depends_on "scipy"

  uses_from_macos "make" => :build

  # Logisim 2.7.1 (GPL-2.0-or-later) is downloaded at install time, never bundled in the sdist.
  # sha256 verified against the upstream SourceForge file and against the jar in Logisim.app 2.7.1.
  resource "logisim-jar" do
    url "https://downloads.sourceforge.net/project/circuit/2.7.x/2.7.1/logisim-generic-2.7.1.jar"
    sha256 "362a78c12ad18c203fed868872c4a01cd9c12141379d92e892bbe2c37e627bc2"
  end

  # Pure-Python dependencies (versions as tested in the project's .venv; sdists from PyPI).
  resource "annotated-doc" do
    url "https://files.pythonhosted.org/packages/5a/8e/38aa427ed5402449e226975b649c5dc73ccadfefeb95e6aecb8f8ea4b6b6/annotated_doc-0.0.5.tar.gz"
    sha256 "c7e58ce09192557605d8bbd92836d7e1d520ac9580096042c0bfd197efacf1bb"
  end

  resource "linkify-it-py" do
    url "https://files.pythonhosted.org/packages/45/98/7a1a5f31fd5c7ba93e963b168e244b8e3dd705b3d2a718e3c3307583bf57/linkify_it_py-2.2.0.tar.gz"
    sha256 "907acd2d17ac1fbb9ddb62c8957ccbd6158cac602231a15c3b0cd1e215f03cee"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/06/ff/7841249c247aa650a76b9ee4bbaeae59370dc8bfd2f6c01f3630c35eb134/markdown_it_py-4.2.0.tar.gz"
    sha256 "04a21681d6fbb623de53f6f364d352309d4094dd4194040a10fd51833e418d49"
  end

  resource "mdit-py-plugins" do
    url "https://files.pythonhosted.org/packages/59/fc/f8d0863f8862f25602c0404d75568e89fb6b4109804645e5cdfb1be5cf56/mdit_py_plugins-0.6.1.tar.gz"
    sha256 "a2bca0f039f39dbd35fb74ae1b5f998608c437463371f0ff7f49a19a17a114d0"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "platformdirs" do
    url "https://files.pythonhosted.org/packages/80/a8/66d45abadff219e36e2a824181b8f6a67e7ed4572934d6252c71c29d5731/platformdirs-4.13.0.tar.gz"
    sha256 "1aa0b0d3f224c1f07c295121e312a5a24a180d6ae5a8425ea1784b3e3863e9c0"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz"
    sha256 "610ca751c9bc2492b38eb9a38a7fbc93edbbb2d7182edaf34e66ae493dee5c8c"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/c0/8f/0722ca900cc807c13a6a0c696dacf35430f72e0ec571c4275d2371fca3e9/rich-15.0.0.tar.gz"
    sha256 "edd07a4824c6b40189fb7ac9bc4c52536e9780fbbfbddf6f1e2502c31b068c36"
  end

  resource "shellingham" do
    url "https://files.pythonhosted.org/packages/58/15/8b3609fd3830ef7b27b655beb4b4e9c62313a4e8da8c676e142cc210d58e/shellingham-1.5.4.tar.gz"
    sha256 "8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de"
  end

  resource "textual" do
    url "https://files.pythonhosted.org/packages/00/21/39a76b01bd5eea82a04baaca7580e105d8c59450df03998345bb2cfb307b/textual-8.2.8.tar.gz"
    sha256 "3f106a9fbc73e39dd266c9712432087de78a6d644084c7c241d6a25c3169115b"
  end

  resource "typer" do
    url "https://files.pythonhosted.org/packages/03/51/d33db42cc72ffd8c30777547b42d01f0cbf9d95a770457698d0174b3ed71/typer-0.27.3.tar.gz"
    sha256 "d0396f770a560ab1b0a8504e13b5f254b728cedb05c61cf0359e944e50ce8901"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz"
    sha256 "dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5"
  end

  def install
    # 1. Python application + pure-Python resources into libexec (numpy/scipy via system site-packages).
    virtualenv_install_with_resources without: "logisim-jar"

    # 2. Berkeley Espresso from the vendored sources (the Makefile writes ../bin/espresso).
    cd "third_party/espresso/espresso-src" do
      system "make", "CC=#{ENV.cc}"
    end
    (libexec/"espresso/bin").install "third_party/espresso/bin/espresso"

    # 3. The pinned Logisim 2.7.1 jar.
    resource("logisim-jar").stage do
      libexec.install "logisim-generic-2.7.1.jar" => "logisim.jar"
    end

    # 4. Compile the Java helper against the pinned jar with Homebrew's JDK. The `built-for` marker names that
    #    jar; logilens uses this prebuilt copy only for that exact jar (another jar -> own cached build).
    mkdir "helper-classes"
    system Formula["openjdk"].opt_bin/"javac", "--release", "11", "-nowarn",
           "-cp", libexec/"logisim.jar", "-d", "helper-classes", "java/LogisimBridge.java"
    (libexec/"helper").install Dir["helper-classes/*.class"]
    (libexec/"helper/built-for").write "#{(libexec/"logisim.jar").realpath}\n"

    # 5. Wrapper: Homebrew's JDK, the pinned jar, the prebuilt helper and Espresso (user values still win).
    env = Language::Java.overridable_java_home_env.merge(
      LOGILENS_HOME:       libexec,
      LOGISIM_JAR:         "${LOGISIM_JAR:-#{libexec}/logisim.jar}",
      LOGILENS_HELPER_DIR: "${LOGILENS_HELPER_DIR:-#{libexec}/helper}",
      LOGILENS_ESPRESSO:   "${LOGILENS_ESPRESSO:-#{libexec}/espresso/bin/espresso}",
    )
    rm bin/"logilens"
    (bin/"logilens").write_env_script libexec/"bin/logilens", env

    # 6. The example circuits from the README quick start (also used by `brew test`).
    (pkgshare/"examples").install Dir["examples/*"]
  end

  def caveats
    <<~EOS
      Check the environment with:
        logilens doctor
      The Logisim helper is prebuilt for the bundled jar; another jar gets its own build on first use.
      Optional: brew install graphviz (pictures of state graphs).
      Example files: #{opt_pkgshare}/examples
    EOS
  end

  test do
    assert_match "logilens #{version}", shell_output("#{bin}/logilens --version")

    doctor = JSON.parse(shell_output("#{bin}/logilens doctor --json"))
    assert doctor["healthy"], "doctor reports an unhealthy environment"
    statuses = doctor["checks"].to_h { |check| [check["name"], check["status"]] }
    %w[python java javac jar espresso].each do |name|
      assert_equal "ok", statuses[name], "doctor check '#{name}' is not ok"
    end

    output = shell_output("#{bin}/logilens --lang en check " \
                          "--spec #{pkgshare}/examples/converter.spec.txt " \
                          "#{pkgshare}/examples/converter_nand_nor.circ")
    assert_match "12/12", output
  end
end
