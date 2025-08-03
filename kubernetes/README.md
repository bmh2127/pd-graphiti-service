# Kubernetes Deployment for PD Graphiti Service

This directory contains Kubernetes manifests for deploying the PD Graphiti Service in a production Kubernetes cluster.

## 📋 Quick Deployment

```bash
# 1. Create namespace and apply base configuration
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-configmap.yaml

# 2. Create secrets (update with your values first)
kubectl apply -f 02-secrets.yaml

# 3. Deploy Neo4j database
kubectl apply -f 10-neo4j-storage.yaml
kubectl apply -f 11-neo4j-statefulset.yaml
kubectl apply -f 12-neo4j-service.yaml

# 4. Deploy application
kubectl apply -f 20-pd-graphiti-deployment.yaml
kubectl apply -f 21-pd-graphiti-service.yaml
kubectl apply -f 22-pd-graphiti-ingress.yaml

# 5. Enable auto-scaling (optional)
kubectl apply -f 30-hpa.yaml

# 6. Setup monitoring (optional)
kubectl apply -f 40-servicemonitor.yaml
```

## 📂 File Structure

| File | Purpose |
|------|---------|
| `00-namespace.yaml` | Kubernetes namespace |
| `01-configmap.yaml` | Application configuration |
| `02-secrets.yaml` | Sensitive configuration (API keys, passwords) |
| `10-neo4j-storage.yaml` | Persistent volumes for Neo4j |
| `11-neo4j-statefulset.yaml` | Neo4j database deployment |
| `12-neo4j-service.yaml` | Neo4j service definition |
| `20-pd-graphiti-deployment.yaml` | Main application deployment |
| `21-pd-graphiti-service.yaml` | Application service definition |
| `22-pd-graphiti-ingress.yaml` | Ingress for external access |
| `30-hpa.yaml` | Horizontal Pod Autoscaler |
| `40-servicemonitor.yaml` | Prometheus monitoring setup |

## ⚙️ Configuration

### Prerequisites

1. **Kubernetes cluster** with:
   - StorageClass for persistent volumes
   - Ingress controller (nginx recommended)
   - Cert-manager (for TLS)

2. **Secrets to configure:**
   - OpenAI API key
   - Neo4j password

### Before Deployment

1. **Update secrets** in `02-secrets.yaml`:
   ```bash
   echo -n "your-openai-api-key" | base64
   echo -n "your-neo4j-password" | base64
   ```

2. **Update ingress** in `22-pd-graphiti-ingress.yaml`:
   - Replace `pd-graphiti.yourdomain.com` with your domain
   - Configure TLS certificates

3. **Review resource limits** based on your cluster capacity

## 🔧 Customization

### Resource Requirements

**Minimum:**
- Neo4j: 2 CPU, 4GB RAM, 50GB storage
- Application: 1 CPU, 2GB RAM

**Production:**
- Neo4j: 4 CPU, 8GB RAM, 200GB storage
- Application: 2 CPU, 4GB RAM (3 replicas)

### Storage Configuration

Update `storageClassName` in persistent volume claims:
```yaml
spec:
  storageClassName: fast-ssd  # Your storage class
```

### Scaling Configuration

Modify HPA in `30-hpa.yaml`:
```yaml
spec:
  minReplicas: 2      # Minimum instances
  maxReplicas: 10     # Maximum instances
  targetCPUUtilizationPercentage: 70
```

## 🚀 Deployment Commands

### Deploy Everything

```bash
# Apply all manifests
kubectl apply -f .

# Watch deployment progress
kubectl get pods -n pd-graphiti -w
```

### Selective Deployment

```bash
# Just the database
kubectl apply -f 00-namespace.yaml -f 01-configmap.yaml -f 02-secrets.yaml
kubectl apply -f 10-neo4j-storage.yaml -f 11-neo4j-statefulset.yaml -f 12-neo4j-service.yaml

# Just the application
kubectl apply -f 20-pd-graphiti-deployment.yaml -f 21-pd-graphiti-service.yaml
```

### Verify Deployment

```bash
# Check pod status
kubectl get pods -n pd-graphiti

# Check services
kubectl get svc -n pd-graphiti

# Check ingress
kubectl get ingress -n pd-graphiti

# View logs
kubectl logs -n pd-graphiti deployment/pd-graphiti-service

# Test health endpoint
kubectl port-forward -n pd-graphiti svc/pd-graphiti-service 8080:80
curl http://localhost:8080/health/live
```

## 🔍 Monitoring

### Prometheus Integration

The ServiceMonitor in `40-servicemonitor.yaml` configures Prometheus scraping:

```bash
# Check metrics
kubectl port-forward -n pd-graphiti svc/pd-graphiti-service 8080:80
curl http://localhost:8080/metrics
```

### Logs

View structured JSON logs:
```bash
# Application logs
kubectl logs -n pd-graphiti deployment/pd-graphiti-service -f

# Neo4j logs
kubectl logs -n pd-graphiti statefulset/neo4j -f

# Filter by log level
kubectl logs -n pd-graphiti deployment/pd-graphiti-service | jq 'select(.level == "error")'
```

## 🛠️ Maintenance

### Scaling

```bash
# Manual scaling
kubectl scale deployment pd-graphiti-service --replicas=5 -n pd-graphiti

# Check HPA status
kubectl get hpa -n pd-graphiti
```

### Updates

```bash
# Update image
kubectl set image deployment/pd-graphiti-service pd-graphiti-service=pd-graphiti-service:v0.2.0 -n pd-graphiti

# Rollback if needed
kubectl rollout undo deployment/pd-graphiti-service -n pd-graphiti

# Check rollout status
kubectl rollout status deployment/pd-graphiti-service -n pd-graphiti
```

### Backup

```bash
# Backup configuration
kubectl get all,pvc,secrets,configmaps -n pd-graphiti -o yaml > pd-graphiti-backup.yaml

# Backup Neo4j data (see backup procedures in main documentation)
```

## 🔒 Security

### Network Policies

The manifests include NetworkPolicies for:
- Restricting ingress traffic
- Limiting egress to required services
- Isolating database access

### Pod Security

All pods run with:
- Non-root user (UID 1001)
- Read-only root filesystem
- Dropped capabilities
- Security context constraints

### Secrets Management

For production, consider:
- External secret management (Vault, AWS Secrets Manager)
- Sealed Secrets for GitOps workflows
- Regular secret rotation

## 🚨 Troubleshooting

### Common Issues

**Pods not starting:**
```bash
kubectl describe pods -n pd-graphiti
kubectl logs -n pd-graphiti deployment/pd-graphiti-service
```

**Storage issues:**
```bash
kubectl get pvc -n pd-graphiti
kubectl describe pvc -n pd-graphiti
```

**Network connectivity:**
```bash
kubectl exec -n pd-graphiti deployment/pd-graphiti-service -- nc -zv neo4j-service 7687
```

**Resource constraints:**
```bash
kubectl top pods -n pd-graphiti
kubectl describe node
```

For detailed troubleshooting, see the main [DEPLOYMENT.md](../DEPLOYMENT.md) guide.