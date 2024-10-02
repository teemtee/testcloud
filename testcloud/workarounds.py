from typing import Optional, Union


class Workarounds:
    def __init__(self, defaults: bool = False) -> None:
        self._workarounds: dict[str, list[str]] = {}
        if defaults:
            self._populate_defaults()
        else:
            self.add("true", key="nocmd")

    def _populate_defaults(self) -> None:
        self.add(
            "sed -i -e '/^.*PermitRootLogin/s/^.*$/PermitRootLogin yes/'"
            " -e '/^.*UseDNS/s/^.*$/UseDNS no/'"
            " -e '/^.*GSSAPIAuthentication/s/^.*$/GSSAPIAuthentication no/' "
            "/etc/ssh/sshd_config",
            key="ssh_config",
        )
        self.add("systemctl reload sshd", key="ssh_reload")
        self.add_condition(
            '[ ! -f /etc/systemd/network/20-tc-usernet.network ] && systemctl status systemd-networkd | grep -q "enabled;\\svendor\\spreset:\\senabled"',
            [
                "mkdir -p /etc/systemd/network/",
                'echo "[Match]" >> /etc/systemd/network/20-tc-usernet.network',
                'echo "Name=en*" >> /etc/systemd/network/20-tc-usernet.network',
                'echo "[Network]" >> /etc/systemd/network/20-tc-usernet.network',
                'echo "DHCP=yes" >> /etc/systemd/network/20-tc-usernet.network',
            ],
            key="user_net_config",
        )
        self.add_condition(
            'systemctl status systemd-networkd | grep -q "enabled;\\svendor\\spreset:\\senabled"',
            "systemctl restart systemd-networkd",
            key="net_restart",
        )
        self.add_os("platform:el8", "systemctl restart sshd", key="el8_net")
        self.add_os(
            "CentOS Linux 7",
            [
                "sed '/mirrorlist/d' -i /etc/yum.repos.d/*repo",
                "sed 's|#baseurl=http://mirror.centos.org/centos/\\$releasever|baseurl=https://vault.centos.org/7.9.2009|' -i /etc/yum.repos.d/*repo",
            ],
            key="el7_vault_repos",
        )
        self.add("dhclient || :", key="dhclient")

    def _generate_key(self) -> str:
        "?? wip"
        import random
        import string

        return "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

    def _create_workaround_cmd(self, cmd: str) -> list[str]:
        return ["sh", "-c", cmd]

    def _parse_cmd(self, cmd: Union[str, list[str]]) -> str:
        if isinstance(cmd, str):
            return cmd
        else:
            return " && ".join(cmd)

    def add(self, cmd: Union[str, list[str]], key: Optional[str] = None) -> None:
        cmd = self._parse_cmd(cmd)
        key = self._generate_key() if not key else key
        self._workarounds[key] = self._create_workaround_cmd(cmd)

    def add_condition(self, condition: str, cmd: Union[str, list[str]], key: Optional[str] = None):
        sh_condition_string = "if %s ; then %s ; fi"
        cmd = self._parse_cmd(cmd)
        self.add(sh_condition_string % (condition, cmd), key=key)

    def add_os(self, os: str, cmd: Union[str, list[str]], key: Optional[str] = None) -> None:
        condition = "cat /etc/os-release | grep -q '%s'" % os
        self.add_condition(condition, cmd, key)

    def remove(self, key: str):
        self._workarounds.pop(key, None)

    def generate_cloud_init_cmd_list(self) -> str:
        cmds = []
        for _, value in self._workarounds.items():
            cmds.append("- " + value.__repr__())
        return "\n".join(cmds)

    def get_all(self) -> dict[str, list[str]]:
        return self._workarounds
