#!/bin/bash

# This script starts mitmdump. We start seven instances, and then monitor them.
# They are relatively unstable and have a tendency to crash, so we restart them
# when that happens. Run as root.

# We may have to think of a proper solution here. And by we unfortunately I
# mean me :(

while [[ true ]]; do 
    for port in `seq 8080 8086`; do
        unset http_proxy
        export http_proxy=unicornbottle-main:$port && wget --timeout 10 -t 1 http://www.example.org/ -qO- >/dev/null
        if [ $? -eq 0 ]; then
            echo -n .
        else
            echo
            echo Proxy not proxying.
            
            if pkill -f -e "mitmdump.*-p $port" >/dev/null; then
                # process exists and hung.
                echo Asked process firmly yet kindly to restart. Checking for compliance.
                sleep 10
                if pkill -9 -f -e "mitmdump.*-p $port">/dev/null; then
                    echo Process very rudely failing to comply, asking for the last time.
                fi
            fi

            ulimit -Hn 1048576 && ulimit -Sn 1048576 && sudo -u httpproxy poetry run mitmdump --set confdir=/opt/mitmdump -s rpc_addon.py --ssl-insecure --no-http2 -q -p $port>/dev/null &
        fi
    done
    sleep 10
done
