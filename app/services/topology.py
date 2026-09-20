"""Валидация 3-tier топологии и генерация Terraform HCL. Без сети."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

from pydantic import BaseModel, Field


class Topology(BaseModel):
    vpc_cidr: str
    public_subnets: list[str] = Field(min_length=1)
    private_subnets: list[str] = Field(min_length=1)
    db_subnets: list[str] = Field(min_length=1)
    allowed_db_sources: list[str] = Field(default_factory=list)


def _parse_cidr(value: str, field: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError(f"{field}: invalid CIDR {value!r}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError(f"{field}: only IPv4 CIDR supported, got {value!r}")
    return network


def validate_topology(topology: Topology) -> list[str]:
    """Проверить топологию. Вернуть список ошибок (пусто — ок)."""
    errors: list[str] = []
    vpc = _parse_cidr(topology.vpc_cidr, "vpc_cidr")
    groups = {
        "public_subnets": topology.public_subnets,
        "private_subnets": topology.private_subnets,
        "db_subnets": topology.db_subnets,
    }
    parsed: dict[str, list[ipaddress.IPv4Network]] = {}
    for name, cidrs in groups.items():
        networks: list[ipaddress.IPv4Network] = []
        for cidr in cidrs:
            try:
                network = _parse_cidr(cidr, name)
            except ValueError:
                errors.append(f"{name}: invalid CIDR {cidr!r}")
                continue
            if not network.subnet_of(vpc):
                errors.append(f"{name}: {cidr} is outside VPC {vpc}")
            networks.append(network)
        if len(networks) < 2:
            errors.append(f"{name}: need subnets in at least 2 AZs, got {len(networks)}")
        parsed[name] = networks
    seen: list[tuple[str, ipaddress.IPv4Network]] = []
    for name, networks in parsed.items():
        for network in networks:
            for other_name, other in seen:
                if network.overlaps(other):
                    errors.append(f"overlap: {name} {network} overlaps {other_name} {other}")
            seen.append((name, network))
    for source in topology.allowed_db_sources:
        try:
            net = _parse_cidr(source, "allowed_db_sources")
        except ValueError:
            errors.append(f"allowed_db_sources: invalid CIDR {source!r}")
            continue
        if net == ipaddress.ip_network("0.0.0.0/0"):
            errors.append("allowed_db_sources: database open to 0.0.0.0/0")
        elif not net.subnet_of(vpc):
            errors.append(f"allowed_db_sources: {source} is outside VPC {vpc}")
    return errors


def load_topology(path: str | Path) -> Topology:
    """Прочитать топологию из JSON."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read topology file: {exc}") from exc
    return Topology.model_validate(data)


def generate_hcl(vpc_cidr: str, azs: int = 2, region: str = "eu-central-1") -> str:
    """Сгенерировать VPC + подсети + SG в HCL. Детерминировано."""
    if azs < 1 or azs > 6:
        raise ValueError("azs must be 1..6")
    vpc = _parse_cidr(vpc_cidr, "vpc_cidr")
    subnets = list(vpc.subnets(new_prefix=vpc.prefixlen + 4))
    need = azs * 3
    if len(subnets) < need:
        raise ValueError(f"CIDR {vpc} too small for {azs} AZs x 3 tiers")
    public = subnets[0:azs]
    private = subnets[azs : azs * 2]
    db = subnets[azs * 2 : azs * 3]
    lines = [
        f'# Generated 3-tier VPC for {vpc} in {region}',
        'terraform { required_version = ">= 1.5" }',
        "",
        'resource "aws_vpc" "main" {',
        f'  cidr_block = "{vpc}"',
        "}",
    ]
    for index, network in enumerate([*public, *private, *db]):
        tier = "public" if index < azs else "private" if index < azs * 2 else "db"
        lines += [
            "",
            f'resource "aws_subnet" "{tier}_{index % azs}" {{',
            '  vpc_id     = aws_vpc.main.id',
            f'  cidr_block = "{network}"',
            f'  availability_zone = "{region}{chr(97 + index % azs)}"',
            f'  map_public_ip_on_launch = {"true" if tier == "public" else "false"}',
            "}",
        ]
    lines += [
        "",
        'resource "aws_security_group" "db" {',
        "  vpc_id = aws_vpc.main.id",
        "  ingress {",
        "    from_port   = 5432",
        "    to_port     = 5432",
        "    protocol    = \"tcp\"",
        f'    cidr_blocks = {[str(net) for net in private]}',
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)
