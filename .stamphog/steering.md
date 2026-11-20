Treat package lifecycle scripts, registry changes, CLI worker templates, Docker
builds and Prisma client generation as executable supply-chain surfaces.
Changes to authentication, billing, runtime isolation or database schemas need
human review. Do not infer application-wide equivalence from the recorded CLI
build: webapp, services, deployment and other unrecorded workloads are omitted.
Missing, stale or incomplete runtime evidence is undeterminable.
