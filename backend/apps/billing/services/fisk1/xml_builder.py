from __future__ import annotations

from decimal import Decimal

from lxml import etree

NS = "http://www.apis-it.hr/fin/2012/types/F73"
NSMAP = {"tns": NS}


def _amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _rate(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def build_racun_xml(
    *,
    oib: str,
    issued_at_iso: str,
    sequence_number: int,
    vat_rate: Decimal,
    vat_base: Decimal,
    vat_amount: Decimal,
    total: Decimal,
    payment_code: str,
    operator_oib: str,
    zki: str,
    business_premise_code: str,
    payment_device_code: str,
) -> etree._Element:
    root = etree.Element(f"{{{NS}}}RacunZahtjev", nsmap=NSMAP)
    root.set("Id", "racun")

    racun = etree.SubElement(root, f"{{{NS}}}Racun")
    etree.SubElement(racun, f"{{{NS}}}Oib").text = oib
    etree.SubElement(racun, f"{{{NS}}}USustPdv").text = "true"
    etree.SubElement(racun, f"{{{NS}}}DatVrijeme").text = issued_at_iso
    etree.SubElement(racun, f"{{{NS}}}OznSlijed").text = "P"
    etree.SubElement(racun, f"{{{NS}}}BrRac").text = str(sequence_number)

    pdv = etree.SubElement(racun, f"{{{NS}}}Pdv")
    porez = etree.SubElement(pdv, f"{{{NS}}}Porez")
    etree.SubElement(porez, f"{{{NS}}}Stopa").text = _rate(vat_rate)
    etree.SubElement(porez, f"{{{NS}}}Osnovica").text = _amount(vat_base)
    etree.SubElement(porez, f"{{{NS}}}Iznos").text = _amount(vat_amount)

    etree.SubElement(racun, f"{{{NS}}}IznosUkupno").text = _amount(total)
    etree.SubElement(racun, f"{{{NS}}}NacinPlac").text = payment_code
    etree.SubElement(racun, f"{{{NS}}}OibOper").text = operator_oib
    etree.SubElement(racun, f"{{{NS}}}ZastKod").text = zki
    etree.SubElement(racun, f"{{{NS}}}OznPosPr").text = business_premise_code
    etree.SubElement(racun, f"{{{NS}}}OznNapUr").text = payment_device_code
    return root


def parse_jir_from_response(xml_text: str) -> str:
    root = etree.fromstring(xml_text.encode("utf-8"))
    for elem in root.iter():
        if elem.tag.endswith("Jir") and elem.text:
            return elem.text.strip()
    raise ValueError("JIR not found in fiscalization response")
