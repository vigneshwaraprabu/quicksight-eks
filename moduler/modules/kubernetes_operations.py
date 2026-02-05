import os
import tempfile
import subprocess
from typing import List, Dict
import kubernetes.client as k8s
import kubernetes.config


class KubernetesOperations:
    
    KUBECONFIG_TIMEOUT = 30
    K8S_API_TIMEOUT = 10
    
    def __init__(self, session, region: str):
        self.session = session
        self.region = region
    
    def get_node_readiness(self, instance_ids: List[str], cluster_name: str) -> Dict[str, str]:
        if not instance_ids:
            return {}
        
        kubeconfig_path = None
        original_env = self._save_environment()
        
        try:
            self._set_credentials()
            kubeconfig_path = self._generate_kubeconfig(cluster_name)
            if not kubeconfig_path:
                return {iid: "Unknown" for iid in instance_ids}
            
            readiness_map = self._query_kubernetes_nodes(kubeconfig_path, instance_ids)
            return readiness_map
            
        except subprocess.TimeoutExpired:
            print(f"WARNING: Timeout accessing cluster '{cluster_name}' ({self.KUBECONFIG_TIMEOUT}s limit)")
            return {iid: "Unknown" for iid in instance_ids}
        except k8s.ApiException as e:
            self._handle_k8s_error(e, cluster_name)
            return {iid: "Unknown" for iid in instance_ids}
        except Exception as e:
            print(f"ERROR: Failed to fetch node readiness for '{cluster_name}': {str(e)}")
            return {iid: "Unknown" for iid in instance_ids}
        finally:
            self._restore_environment(original_env)
            self._cleanup_kubeconfig(kubeconfig_path)
    
    def _save_environment(self) -> Dict[str, str]:
        return {
            'AWS_ACCESS_KEY_ID': os.environ.get('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'AWS_SESSION_TOKEN': os.environ.get('AWS_SESSION_TOKEN'),
            'AWS_DEFAULT_REGION': os.environ.get('AWS_DEFAULT_REGION')
        }
    
    def _set_credentials(self):
        creds = self.session.get_credentials().get_frozen_credentials()
        os.environ.update({
            'AWS_ACCESS_KEY_ID': creds.access_key,
            'AWS_SECRET_ACCESS_KEY': creds.secret_key,
            'AWS_SESSION_TOKEN': creds.token,
            'AWS_DEFAULT_REGION': self.region
        })
    
    def _restore_environment(self, original_env: Dict[str, str]):
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    
    def _generate_kubeconfig(self, cluster_name: str) -> str:
        try:
            with tempfile.NamedTemporaryFile(delete=False, mode='w') as tmp:
                kubeconfig_path = tmp.name
            
            print(f"INFO: Generating kubeconfig for cluster '{cluster_name}'")
            result = subprocess.run(
                ["aws", "eks", "update-kubeconfig", "--name", cluster_name, 
                 "--region", self.region, "--kubeconfig", kubeconfig_path],
                capture_output=True,
                text=True,
                timeout=self.KUBECONFIG_TIMEOUT
            )
            
            if result.returncode != 0:
                print(f"ERROR: Failed to generate kubeconfig: {result.stderr}")
                return None
            
            return kubeconfig_path
        except Exception as e:
            print(f"ERROR: Kubeconfig generation failed: {e}")
            return None
    
    def _query_kubernetes_nodes(self, kubeconfig_path: str, instance_ids: List[str]) -> Dict[str, str]:
        kubernetes.config.load_kube_config(config_file=kubeconfig_path)
        
        api_client = k8s.ApiClient()
        api_client.rest_client.pool_manager.connection_pool_kw['timeout'] = self.K8S_API_TIMEOUT
        v1 = k8s.CoreV1Api(api_client)
        
        print("INFO: Querying Kubernetes API for node status")
        k8s_nodes = v1.list_node(_request_timeout=self.K8S_API_TIMEOUT)
        
        readiness_map = {}
        for node in k8s_nodes.items:
            provider_id = node.spec.provider_id
            if provider_id and provider_id.startswith("aws:///"):
                instance_id = provider_id.split("/")[-1]
                if instance_id in instance_ids:
                    conditions = node.status.conditions or []
                    ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
                    readiness_map[instance_id] = "Ready" if ready else "NotReady"
        
        for iid in instance_ids:
            readiness_map.setdefault(iid, "Unknown")
        
        return readiness_map
    
    @staticmethod
    def _handle_k8s_error(error: k8s.ApiException, cluster_name: str):
        error_map = {
            401: f"ERROR: Unauthorized access to cluster '{cluster_name}'. Check EKS access entries",
            403: f"ERROR: Forbidden access to cluster '{cluster_name}'. Check IAM permissions",
        }
        message = error_map.get(error.status, f"ERROR: Kubernetes API error for cluster '{cluster_name}': {error.reason}")
        print(message)
    
    @staticmethod
    def _cleanup_kubeconfig(kubeconfig_path: str):
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            try:
                os.remove(kubeconfig_path)
            except Exception:
                pass
