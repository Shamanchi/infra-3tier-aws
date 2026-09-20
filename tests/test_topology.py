"""Unit-тесты валидации и генерации: без сети, детерминированы."""

import pytest

from app.services.topology import Topology, generate_hcl, validate_topology


def _valid() -> Topology:
    return Topology(
        vpc_cidr="10.0.0.0/16",
        public_subnets=["10.0.1.0/24", "10.0.2.0/24"],
        private_subnets=["10.0.11.0/24", "10.0.12.0/24"],
        db_subnets=["10.0.21.0/24", "10.0.22.0/24"],
        allowed_db_sources=["10.0.11.0/24", "10.0.12.0/24"],
    )


def test_valid_topology() -> None:
    assert validate_topology(_valid()) == []


def test_overlap_detected() -> None:
    topo = _valid()
    topo.private_subnets = ["10.0.1.0/24", "10.0.12.0/24"]
    errors = validate_topology(topo)
    assert any("overlap" in error for error in errors)


def test_open_db_rejected() -> None:
    topo = _valid()
    topo.allowed_db_sources = ["0.0.0.0/0"]
    errors = validate_topology(topo)
    assert any("0.0.0.0/0" in error for error in errors)


def test_single_az_rejected() -> None:
    topo = _valid()
    topo.db_subnets = ["10.0.21.0/24"]
    errors = validate_topology(topo)
    assert any("2 AZs" in error for error in errors)


def test_outside_vpc_rejected() -> None:
    topo = _valid()
    topo.public_subnets = ["192.168.1.0/24", "10.0.2.0/24"]
    errors = validate_topology(topo)
    assert any("outside VPC" in error for error in errors)


def test_generate_hcl() -> None:
    hcl = generate_hcl("10.0.0.0/16", azs=2)
    assert 'resource "aws_vpc" "main"' in hcl
    assert hcl.count('resource "aws_subnet"') == 6
    assert 'resource "aws_security_group" "db"' in hcl
    with pytest.raises(ValueError):
        generate_hcl("10.0.0.0/16", azs=0)
