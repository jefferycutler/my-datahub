# My Datahub Kubernetes Infrastructure

## Deployment

### Prerequisites
- `kubectl` configured
- `helm` installed

### 1. Namespaces
Create the required namespaces:
```bash
kubectl apply -f namespaces.yaml
```

### 2. Kubernetes Dashboard
Install the Kubernetes Dashboard:
```bash
helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard
helm repo update
helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
    -n kubernetes-dashboard --create-namespace \
    -f charts/kubernetes-dashboard/values.yaml
```

#### Access
1. Create Admin User (if not already done):
   ```bash
   kubectl apply -f dashboard-admin.yaml
   ```
2. Generate Token:
   ```bash
   kubectl -n kubernetes-dashboard create token admin-user
   ```
3. Port Forward:
   ```bash
   kubectl -n kubernetes-dashboard port-forward svc/kubernetes-dashboard-kong-proxy 8443:443
   ```
4. Open https://localhost:8443 and login with the token.


### 3. Kafka UI
Install the Kafka UI:
```bash
helm repo add kafka-ui https://provectus.github.io/kafka-ui-charts
helm repo update
helm upgrade --install kafka-ui kafka-ui/kafka-ui \
    -n kafka-ui --create-namespace \
    -f charts/kafka-ui/values.yaml
```