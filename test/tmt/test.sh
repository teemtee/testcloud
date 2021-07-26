#!/bin/bash
. /usr/share/beakerlib/beakerlib.sh || exit 1

rlJournalStart
    rlPhaseStartSetup
        rlAssertRpm "tmt"
        rlAssertRpm "python3-testcloud"
        rlRun "useradd tester"
        rlRun "tmp=\$(mktemp -d)" 0 "Create tmp directory"
        rlRun "cp plan.txt $tmp/plan.fmf"
        rlRun "chown -R tester /var/tmp/tmt $tmp"
    rlPhaseEnd

    for image in fedora centos; do
        rlPhaseStartTest "Test $image"
            rlRun "su -l tester -c 'cd $tmp && tmt init'"
            rlRun "su -l tester -c \
                'cd $tmp && tmt run -avvvddd provision -h virtual -i $image'"
        rlPhaseEnd
    done

    rlPhaseStartCleanup
        rlRun "pkill -U tester"
        rlRun "userdel -r tester"
        rlRun "rm -r $tmp" 0 "Remove tmp directory"
    rlPhaseEnd
rlJournalEnd
