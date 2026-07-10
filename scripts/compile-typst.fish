#!/usr/bin/env fish
# Compile a Typst file to PDF.
# Usage: compile-typst <path-to-file.typ> [output.pdf]
#   Output defaults to /tmp/<basename>.pdf
#   The Typst project root is set to the parent of the file's directory
#   (so imports like ../lib/... resolve correctly).

set src (realpath $argv[1])
set src_dir (dirname $src)
set root (dirname $src_dir)

if set -q argv[2]
    set out "$argv[2]"
else
    set base (basename $src .typ)
    set out "/tmp/$base.pdf"
end

typst compile --root $root $src $out
echo $out
