# Security policy

logilens reads `.circ` files on your machine. It may run a Java helper against your Logisim jar and a
locally built Espresso binary. logilens makes no network connections of its own. The Homebrew formula and
`scripts/install.sh --download-jar` download Logisim 2.7.1 once and check it against a pinned SHA-256.

Please report vulnerabilities privately through GitHub: Security tab → "Report a vulnerability".
Don't open a public issue for them.

Only the latest release gets fixes. This is a one-person project, so replies are best effort, usually
within two weeks.

A crash or a wrong result on a malformed `.circ` file is an ordinary bug; open an issue for that.
`.circ` files with a DTD or entity declarations are rejected before parsing, so an XML bomb or a similar
file that gets past that check is a security problem; report it privately as described above.
