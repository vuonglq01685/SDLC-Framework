# Architecture Overview

## C4 Context Diagram

This document describes the system architecture using C4 model notation.

## ADR-001: Use PostgreSQL for persistence

**Status**: Accepted

**Context**: We need a reliable RDBMS for customer data.

**Decision**: Use PostgreSQL 15+.

## Component Diagram

The service exposes REST endpoints and connects to a PostgreSQL instance.
