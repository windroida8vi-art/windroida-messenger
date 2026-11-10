#!/bin/bash
# Compiles the Kotlin network core and runs NetTest against a throw-away Windroida server (needs kotlinc in KT, default /tmp/kt/kotlinc)
KT=${KT:-/tmp/kt/kotlinc}; HERE=$(cd "$(dirname "$0")" && pwd); OUT=${OUT:-/tmp/kt/out}
export PATH=$KT/bin:$PATH
rm -rf $OUT $OUT-test && kotlinc -nowarn -jvm-target 17 -d $OUT $HERE/../app/src/main/java/ir/windroida/app/net/*.kt 2>&1 | grep -v JAVA_TOOL
kotlinc -nowarn -jvm-target 17 -cp $OUT -d $OUT-test $HERE/NetTest.kt $HERE/ModelTest.kt 2>&1 | grep -v JAVA_TOOL
( python3 $HERE/run_server.py < <(sleep 100) > /tmp/kt/srv.log 2>&1 & )
for i in 1 2 3 4 5 6 7 8; do P=$(grep PORT /tmp/kt/srv.log 2>/dev/null | awk '{print $2}'); [ -n "$P" ] && break; sleep 1; done
MODE=$(grep PORT /tmp/kt/srv.log | awk '{print $3}'); [ "$MODE" = TLS ] && ARG=TLS
timeout 90 java -cp "$OUT-test:$OUT:$KT/lib/kotlin-stdlib.jar" ${MAIN:-NetTestKt} $P $ARG 2>&1 | grep -v JAVA_TOOL
