#!/usr/bin/env fish
# Convert target.dj to an English .docx file.
# Usage: dj2docx.fish <path-to-target.dj> [output.docx]
#   Output defaults to /tmp/<parent-dirname>-英文.docx.

function usage
    echo "Usage: dj2docx.fish <path-to-target.dj> [output.docx]" >&2
end

set argc (count $argv)
if test $argc -lt 1; or test $argc -gt 2
    usage
    exit 64
end

if not type -q pandoc
    echo "error: pandoc is required but was not found on PATH" >&2
    exit 127
end

if not test -f "$argv[1]"
    echo "error: input is not a regular file: $argv[1]" >&2
    exit 66
end
if not test -r "$argv[1]"
    echo "error: input is not readable: $argv[1]" >&2
    exit 66
end

set tgt (realpath -- "$argv[1]")
set resolve_status $status
if test $resolve_status -ne 0
    exit $resolve_status
end

if test $argc -eq 2
    set requested_out "$argv[2]"
else
    set parent (basename -- (dirname -- "$tgt"))
    set requested_out "/tmp/$parent-英文.docx"
end

if test -d "$requested_out"
    echo "error: output path is a directory: $requested_out" >&2
    exit 73
end
set out_parent (dirname -- "$requested_out")
if not test -d "$out_parent"
    echo "error: output directory does not exist: $out_parent" >&2
    exit 73
end
if not test -w "$out_parent"
    echo "error: output directory is not writable: $out_parent" >&2
    exit 73
end

set out_dir (realpath -- "$out_parent")
set resolve_status $status
if test $resolve_status -ne 0
    exit $resolve_status
end
set out_name (basename -- "$requested_out")
set out "$out_dir/$out_name"

if test "$tgt" = "$out"
    echo "error: input and output paths must differ" >&2
    exit 64
end

set -g _mpi_tmp_file ""
set -g _mpi_tmp_dir ""
function _mpi_cleanup_dj2docx --on-event fish_exit
    if set -q _mpi_tmp_file; and test -n "$_mpi_tmp_file"; and test -e "$_mpi_tmp_file"
        command rm -f -- "$_mpi_tmp_file"
    end
    if set -q _mpi_tmp_dir; and test -n "$_mpi_tmp_dir"; and test -d "$_mpi_tmp_dir"
        command rmdir -- "$_mpi_tmp_dir" 2>/dev/null
    end
end

set -g _mpi_tmp_dir (command mktemp -d "$out_dir/.dj2docx.XXXXXX")
set temp_status $status
if test $temp_status -ne 0
    exit $temp_status
end
set -g _mpi_tmp_file "$_mpi_tmp_dir/$out_name"

command pandoc "$tgt" -f djot -t docx -o "$_mpi_tmp_file"
set tool_status $status
if test $tool_status -ne 0
    exit $tool_status
end
if not test -s "$_mpi_tmp_file"
    echo "error: pandoc produced an empty DOCX file" >&2
    exit 65
end

command mv -f -- "$_mpi_tmp_file" "$out"
set replace_status $status
if test $replace_status -ne 0
    exit $replace_status
end
set -g _mpi_tmp_file ""
command rmdir -- "$_mpi_tmp_dir" 2>/dev/null
set -g _mpi_tmp_dir ""

echo "$out"
