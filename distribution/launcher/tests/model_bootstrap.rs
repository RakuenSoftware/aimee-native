//! Real TLS transport for approved-model bootstrap; no GPU or production secrets.
use aimee_native_launcher::delivery::bootstrap_for_model;
use std::{
    fs,
    io::{BufRead, BufReader},
    process::{Command, Stdio},
    time::Duration,
};

struct Server(std::process::Child);
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[test]
fn selected_bootstrap_checks_returned_identity_over_verified_tls() {
    let temp = tempfile::tempdir().unwrap();
    let cert = temp.path().join("cert.pem");
    let key = temp.path().join("key.pem");
    let output = Command::new("openssl")
        .args([
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-addext",
            "basicConstraints=critical,CA:FALSE",
            "-keyout",
            key.to_str().unwrap(),
            "-out",
            cert.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    let script = r#"
import http.server,json,ssl,sys,urllib.parse
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        model=query.get('model',['default'])[0]
        if model=='deny':
            self.send_error(403);return
        body=json.dumps({'schema':1,'recipient':'fixture','model': 'wrong' if model=='mismatch' else model,'model_config_sha256':'a'*64}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=http.server.HTTPServer(('127.0.0.1',0),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(sys.argv[1],sys.argv[2])
server.socket=context.wrap_socket(server.socket,server_side=True)
print(server.server_port,flush=True)
server.serve_forever()
"#;
    let mut server = Server(
        Command::new("python3")
            .args([
                "-u",
                "-c",
                script,
                cert.to_str().unwrap(),
                key.to_str().unwrap(),
            ])
            .stdout(Stdio::piped())
            .spawn()
            .unwrap(),
    );
    let mut port = String::new();
    BufReader::new(server.0.stdout.take().unwrap())
        .read_line(&mut port)
        .unwrap();
    let port: u16 = port.trim().parse().unwrap();
    let client = reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(5))
        .add_root_certificate(reqwest::Certificate::from_pem(&fs::read(cert).unwrap()).unwrap())
        .resolve("localhost", ([127, 0, 0, 1], port).into())
        .build()
        .unwrap();
    let endpoint = format!("https://localhost:{port}");
    let call = |model| bootstrap_for_model(&client, &endpoint, "fixture-token", model);
    assert_eq!(call(None).unwrap().model, "default");
    assert_eq!(
        call(Some("family/model+variant")).unwrap().model,
        "family/model+variant"
    );
    assert!(call(Some("mismatch")).is_err());
    assert!(call(Some("deny")).is_err());
    assert!(call(Some("")).is_err());
    assert!(call(Some(&"x".repeat(257))).is_err());
}
