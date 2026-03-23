from services.common.normalization.schemas import NormalizedCommandOutput


def test_normalized_command_output_requires_vendor_and_command():
    model = NormalizedCommandOutput(
        vendor="cisco_ios",
        command="show version",
        records=[{"hostname": "r1"}],
        parser_method="textfsm",
    )
    assert model.vendor == "cisco_ios"
