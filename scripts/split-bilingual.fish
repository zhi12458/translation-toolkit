#!/usr/bin/env fish
# Split combined bilingual .dj into source.dj (CN) and target.dj (EN)
# Usage: split-bilingual.fish <combined.dj>
# Output: source.dj and target.dj in same directory, paragraphs separated by blanks

set dj (realpath $argv[1])
set dir (dirname $dj)

rm -f "$dir/source.dj" "$dir/target.dj"

for line in (cat $dj)
    if string match -qr '[\x{4e00}-\x{9fff}]' -- $line
        echo $line >> "$dir/source.dj"
        echo >> "$dir/source.dj"
    else if test -n (string trim -- $line)
        echo $line >> "$dir/target.dj"
        echo >> "$dir/target.dj"
    end
end

echo "source.dj: $dir/source.dj"
echo "target.dj: $dir/target.dj"
