# Upstream sources and adaptation

| Source | Pinned reference |
|---|---|
| Official PHP 7.4 minimal correction | [712e60f9edfd03f0960fc4fc3c2c375f42b90aa2](https://github.com/php/php-src/commit/712e60f9edfd03f0960fc4fc3c2c375f42b90aa2) |
| Shivam Mathur's PHP 7.2 port | [cd56a87e0ed5448c94d4a82dc9b87b805b3098cd](https://github.com/shivammathur/php-src-backports/commit/cd56a87e0ed5448c94d4a82dc9b87b805b3098cd) |
| Ubuntu source package and archive checksums | [php7.2 7.2.24-0ubuntu0.18.04.17](https://launchpad.net/ubuntu/+source/php7.2/7.2.24-0ubuntu0.18.04.17) |

The target source is the Ubuntu orig/debian source with all **95 vendor
patches** already applied. This is not a patch for an arbitrary pristine PHP
7.2 tree, PPA build, or other distribution revision.

The security patch changes 16 files. For the 14 files outside the VM definition
and generated header, the sequence of added/deleted lines matches Shivam's
pinned security commit. Context and vendor baseline differences are excluded
from that comparison; this does not mean the complete files are identical.

`Zend/zend_vm_def.h` adapts CONCAT/FAST_CONCAT while preserving the Ubuntu
overflow checks. `Zend/zend_vm_execute.h` is regenerated using that PHP 7.2
source's own VM generator. Existing vendor overflow checks and multipart limits
are preserved. No unrelated changes from the fork are imported.

`manifest.json` pins the security patch, vendor patch series, and all 16 source
files before/after the patch. Preparing source and regenerating the VM must
reproduce those hashes; a mismatch stops the workflow.

The correction uses immediate process termination for OOM, avoids early session
upload-progress access, and protects request/array/VM state. It does not disable
all normal uploads. Immediate OOM termination can bypass session persistence
and shutdown callbacks; applications need validation for their own workflows.

Build metadata uses a generic `local1` marker plus a unique rebuild timestamp.
It does not change the C patch. SAPI defaults retain `/etc` and
`/etc/php/7.2/{cli,cgi,fpm}`, NTS/API20170718, and the existing shared extensions.
This narrowly scoped backport does not restore support for an EOL runtime.
