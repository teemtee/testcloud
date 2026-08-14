#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlAssertRpm "tmt"
        rlAssertRpm "python3-testcloud"
        rlRun "useradd tester"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "run=\$(mktemp -d)" 0 "Create run directory"
        rlRun "cp -a data/. $tmp"
        rlRun "chown -R tester $tmp $run"
        [[ -d /var/tmp/tmt ]] && rlRun "chown -R tester /var/tmp/tmt"
    rlPhaseEnd

    rlPhaseStartTest
        rlRun "su -l tester -c 'cd $tmp && tmt run --id $run -avvv'"
    rlPhaseEnd

    rlPhaseStartCleanup
        rlRun "pkill -U tester"
        rlRun "userdel -r tester"
        rlGetTestState || rlFileSubmit "$run/log.txt"
        rlRun "rm -r $tmp $run" 0 "Remove tmp and run directory"
    rlPhaseEnd
rlJournalEnd
