//! The ordinary Aimee profile pins an exact leaf, including behind NAT.
//! TLS handshake signatures still prove possession of that leaf's private key.
use anyhow::{Result, ensure};
use rustls::{CertificateError, DigitallySignedStruct, Error, SignatureScheme,
    client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier},
    crypto::{WebPkiSupportedAlgorithms, verify_tls12_signature, verify_tls13_signature},
    pki_types::{CertificateDer, PrivateKeyDer, ServerName, UnixTime, pem::PemObject}};
use std::sync::Arc;

#[derive(Debug)]
struct PinnedLeaf {
    der: CertificateDer<'static>,
    algorithms: WebPkiSupportedAlgorithms,
}
impl ServerCertVerifier for PinnedLeaf {
    fn verify_server_cert(&self, end_entity: &CertificateDer<'_>, _: &[CertificateDer<'_>],
                         _: &ServerName<'_>, _: &[u8], _: UnixTime) -> std::result::Result<ServerCertVerified, Error> {
        if end_entity.as_ref() != self.der.as_ref() {
            return Err(Error::InvalidCertificate(CertificateError::ApplicationVerificationFailure));
        }
        // Match core's strict TOFU leaf policy: SAN/chain/time do not replace
        // the enrolled pin. Signature verification below is never bypassed.
        Ok(ServerCertVerified::assertion())
    }
    fn verify_tls12_signature(&self, message: &[u8], cert: &CertificateDer<'_>,
                              signature: &DigitallySignedStruct) -> std::result::Result<HandshakeSignatureValid, Error> {
        verify_tls12_signature(message, cert, signature, &self.algorithms)
    }
    fn verify_tls13_signature(&self, message: &[u8], cert: &CertificateDer<'_>,
                              signature: &DigitallySignedStruct) -> std::result::Result<HandshakeSignatureValid, Error> {
        verify_tls13_signature(message, cert, signature, &self.algorithms)
    }
    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> { self.algorithms.supported_schemes() }
}

pub(crate) fn config(pin: &[u8], identity: &[u8]) -> Result<rustls::ClientConfig> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let der = CertificateDer::from_pem_slice(pin)?;
    let chain: Vec<_> = CertificateDer::pem_slice_iter(identity).collect::<std::result::Result<_,_>>()?;
    ensure!(!chain.is_empty(), "missing enrolled client certificate");
    let key = PrivateKeyDer::from_pem_slice(identity)?;
    Ok(rustls::ClientConfig::builder_with_provider(provider.clone()).with_safe_default_protocol_versions()?
        .dangerous().with_custom_certificate_verifier(Arc::new(PinnedLeaf {
            der, algorithms: provider.signature_verification_algorithms,
        })).with_client_auth_cert(chain,key)?)
}
