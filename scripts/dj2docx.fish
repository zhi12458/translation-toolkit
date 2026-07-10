#!/usr/bin/env fish
# Convert target.dj to English docx
# Usage: dj2docx <path-to-target.dj> [output-filename]
#   Output filename defaults to /tmp/<parent-dirname>-英文.docx

set tgt (realpath $argv[1])
if set -q argv[2]
    set out "$argv[2]"
else
    set parent (basename (dirname $tgt))
    set out "/tmp/$parent-英文.docx"
end
pandoc $tgt -f djot -t docx -o $out
echo $out
