from services.agent.agent.normalizer_textfsm.textfsm_parser import TextFSMParser


def test_resolve_template_returns_known_vendor_template():
    parser = TextFSMParser()
    template = parser.resolve_template("cisco_ios", "show version")
    assert template is not None
