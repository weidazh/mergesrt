#!/bin/sh

for d in $(find tests/ -type d); do
    if ls $d/*.srt; then
	if ! python mergesrt.py $d/*.srt > /tmp/test.srt; then
	    echo >&2 "The output is in /tmp/test.srt"
	    break
	fi
    fi
done
