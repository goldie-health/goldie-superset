# Current git state

tag: `6.0.0rc4`
commit: `6a1c30e5e7c3e28d0549c9c2ac0ff61607f26a2f`

# Update Superset flow

```bash
git fetch upstream
git checkout dev # prod
git rebase upstream/master
```

# Build image

## Dev

```bash
docker build --platform linux/amd64 --target lean -t dev-goldie-superset .
```

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <your-ecr-repository-url>
docker build -t dev-goldie-superset .
docker tag dev-goldie-superset:latest <your-ecr-repository-url>/dev-goldie-superset:latest
docker push <your-ecr-repository-url>/dev-goldie-superset:latest
```