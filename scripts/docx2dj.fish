#!/usr/bin/env fish
# Convert .docx to .dj (djot) via pandoc
# Usage: docx2dj.fish <input.docx> [output.dj]
#   No output path → stdout

set docx (realpath $argv[1])

if test (count $argv) -ge 2
    pandoc $docx -f docx -t djot --wrap=none -o $argv[2]
    echo $argv[2]
else
    pandoc $docx -f docx -t djot --wrap=none
end
