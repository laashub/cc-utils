import logging
import urllib.parse

import google.cloud.devtools.containeranalysis_v1
import grafeas.grafeas_v1
import grafeas.grafeas_v1.gapic.transports.grafeas_grpc_transport

import container.registry
import model.container_registry

gcrp_transport = grafeas.grafeas_v1.gapic.transports.grafeas_grpc_transport
container_analysis_v1 = google.cloud.devtools.containeranalysis_v1

logger = logging.getLogger(__name__)


class VulnerabilitiesRetrievalFailed(RuntimeError):
    pass


def grafeas_client(container_registry_cfg: model.container_registry.ContainerRegistryConfig):
    credentials = container_registry_cfg.credentials()

    service_address = container_analysis_v1.ContainerAnalysisClient.SERVICE_ADDRESS
    default_oauth_scope = (
        'https://www.googleapis.com/auth/cloud-platform',
    )
    transport = gcrp_transport.GrafeasGrpcTransport(
        address=service_address,
        scopes=default_oauth_scope, # XXX hard-code for now
        credentials=credentials.service_account_credentials(),
    )

    return grafeas.grafeas_v1.GrafeasClient(transport)


def retrieve_vulnerabilities(image_reference: str, cvss_threshold: int=7.0):
    image_reference = container.registry.normalise_image_reference(image_reference)
    # XXX: should tell required privilege (-> read-vulnerabilities)
    registry_cfg = model.container_registry.find_config(image_reference=image_reference)
    if not registry_cfg:
        raise VulnerabilitiesRetrievalFailed('no registry-cfg found')

    logger.info(f'using {registry_cfg.name()}')

    client = grafeas_client(container_registry_cfg=registry_cfg)

    # XXX / HACK: assuming we always handle GCRs (we should rather check!), the first URL path
    # element is the GCR project name
    project_name = urllib.parse.urlparse(image_reference).path.split('/')[1]
    try:
        hash_reference = container.registry.to_hash_reference(image_reference)
    except Exception as e:
        raise VulnerabilitiesRetrievalFailed(e)

    logger.info(f'retrieving vulnerabilites for {project_name} / {hash_reference}')

    filter_str = f'resourceUrl = "https://{hash_reference}" AND kind="VULNERABILITY"'

    try:
        for r in client.list_occurrences(f'projects/{project_name}', filter_=filter_str):
            # r has type grafeas.grafeas_v1.types.Occurrence
            vuln = r.vulnerability # grafeas.grafeas_v1.types.VulnerabilityOccurrence
            if not hasattr(vuln, 'cvss_score'):
                continue
            if vuln.cvss_score >= cvss_threshold:
                yield r
    except Exception as e:
        raise VulnerabilitiesRetrievalFailed(e)