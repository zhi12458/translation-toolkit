#!/usr/bin/env fish
# Split canonical gen-bilingual.py output into source.dj and target.dj.
# Usage: split-bilingual.fish <combined.dj>
# Output: source.dj and target.dj in the same directory.

function usage
    echo "Usage: split-bilingual.fish <combined.dj>" >&2
end

if test (count $argv) -ne 1
    usage
    exit 64
end

if not test -f "$argv[1]"
    echo "error: input is not a regular file: $argv[1]" >&2
    exit 66
end
if not test -r "$argv[1]"
    echo "error: input is not readable: $argv[1]" >&2
    exit 66
end

set dj (realpath -- "$argv[1]")
set resolve_status $status
if test $resolve_status -ne 0
    exit $resolve_status
end
set dir (dirname -- "$dj")
set source_out "$dir/source.dj"
set target_out "$dir/target.dj"

# Never allow the source of the split to be overwritten by one of its outputs.
# realpath above also catches aliases/symlinks that resolve to these paths.
if test "$dj" = "$source_out"; or test "$dj" = "$target_out"
    echo "error: input must not be source.dj or target.dj" >&2
    exit 64
end
if test -d "$source_out"; or test -d "$target_out"
    echo "error: source.dj and target.dj output paths must not be directories" >&2
    exit 73
end
if not test -w "$dir"
    echo "error: output directory is not writable: $dir" >&2
    exit 73
end

set -g _mpi_tmp_dir ""
set -g _mpi_source_tmp ""
set -g _mpi_target_tmp ""
set -g _mpi_source_backup ""
function _mpi_cleanup_split_bilingual --on-event fish_exit
    for candidate in "$_mpi_source_tmp" "$_mpi_target_tmp" "$_mpi_source_backup"
        if test -n "$candidate"; and test -e "$candidate"
            command rm -f -- "$candidate"
        end
    end
    if set -q _mpi_tmp_dir; and test -n "$_mpi_tmp_dir"; and test -d "$_mpi_tmp_dir"
        command rmdir -- "$_mpi_tmp_dir" 2>/dev/null
    end
end

set -g _mpi_tmp_dir (command mktemp -d "$dir/.split-bilingual.XXXXXX")
set temp_status $status
if test $temp_status -ne 0
    exit $temp_status
end
set -g _mpi_source_tmp "$_mpi_tmp_dir/source.new.dj"
set -g _mpi_target_tmp "$_mpi_tmp_dir/target.new.dj"

command touch -- "$_mpi_source_tmp" "$_mpi_target_tmp"
set touch_status $status
if test $touch_status -ne 0
    exit $touch_status
end

set write_status 0
set pair_state source
set separator_seen 0
set pair_count 0
while read -l line
    set trimmed_line (string trim -- "$line")
    if test -z "$trimmed_line"
        switch "$pair_state"
            case source
                # Leading or structural source blank: preserve it in both files.
                printf '\n' >> "$_mpi_source_tmp"
                set write_status $status
                if test $write_status -eq 0
                    printf '\n' >> "$_mpi_target_tmp"
                    set write_status $status
                end
            case target
                echo "error: source line has no paired target line" >&2
                set write_status 65
            case after_target
                if test $separator_seen -eq 0
                    # The first blank terminates the generated bilingual pair.
                    set separator_seen 1
                else
                    # Additional blanks encode structural blanks in both inputs.
                    printf '\n' >> "$_mpi_source_tmp"
                    set write_status $status
                    if test $write_status -eq 0
                        printf '\n' >> "$_mpi_target_tmp"
                        set write_status $status
                    end
                end
        end
    else
        switch "$pair_state"
            case source
                printf '%s\n' "$line" >> "$_mpi_source_tmp"
                set write_status $status
                set pair_state target
            case target
                printf '%s\n' "$line" >> "$_mpi_target_tmp"
                set write_status $status
                set pair_state after_target
                set separator_seen 0
                set pair_count (math $pair_count + 1)
            case after_target
                if test $separator_seen -eq 0
                    echo "error: bilingual pair is not followed by a blank separator" >&2
                    set write_status 65
                else
                    printf '%s\n' "$line" >> "$_mpi_source_tmp"
                    set write_status $status
                    set pair_state target
                end
        end
    end

    if test $write_status -ne 0
        break
    end
end < "$dj"

if test $write_status -ne 0
    exit $write_status
end
if test "$pair_state" = target
    echo "error: final source line has no paired target line" >&2
    exit 65
end
if test "$pair_state" = after_target; and test $separator_seen -eq 0
    echo "error: final bilingual pair is missing its blank separator" >&2
    exit 65
end
if test $pair_count -eq 0
    echo "error: input contains no complete bilingual pairs" >&2
    exit 65
end
if not test -s "$_mpi_source_tmp"; or not test -s "$_mpi_target_tmp"
    echo "error: split output is empty" >&2
    exit 65
end

# Keep the previous source available for rollback until both atomic renames
# succeed. Existing outputs stay in place while parsing and validation run.
if test -e "$source_out"
    set -g _mpi_source_backup "$_mpi_tmp_dir/source.previous.dj"
    command cp -p -- "$source_out" "$_mpi_source_backup"
    set backup_status $status
    if test $backup_status -ne 0
        exit $backup_status
    end
end

command mv -f -- "$_mpi_source_tmp" "$source_out"
set source_replace_status $status
if test $source_replace_status -ne 0
    exit $source_replace_status
end
set -g _mpi_source_tmp ""

command mv -f -- "$_mpi_target_tmp" "$target_out"
set target_replace_status $status
if test $target_replace_status -ne 0
    if test -n "$_mpi_source_backup"; and test -e "$_mpi_source_backup"
        command mv -f -- "$_mpi_source_backup" "$source_out"
        set rollback_status $status
        if test $rollback_status -eq 0
            set -g _mpi_source_backup ""
        else
            set recovery_path "$_mpi_source_backup"
            # Keep the only recovery copy; clearing the cleanup variable makes
            # the fish_exit handler leave this file in the temporary directory.
            set -g _mpi_source_backup ""
            echo "error: target replace failed ($target_replace_status) and source rollback failed ($rollback_status); previous source retained at $recovery_path" >&2
            exit 74
        end
    else
        command rm -f -- "$source_out"
        set rollback_status $status
        if test $rollback_status -ne 0
            echo "error: target replace failed ($target_replace_status) and new source cleanup failed ($rollback_status): $source_out" >&2
            exit 74
        end
    end
    exit $target_replace_status
end
set -g _mpi_target_tmp ""

if test -n "$_mpi_source_backup"; and test -e "$_mpi_source_backup"
    command rm -f -- "$_mpi_source_backup"
end
set -g _mpi_source_backup ""
command rmdir -- "$_mpi_tmp_dir" 2>/dev/null
set -g _mpi_tmp_dir ""

echo "source.dj: $source_out"
echo "target.dj: $target_out"
