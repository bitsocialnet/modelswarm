import type { ReactNode } from 'react';
import { doc } from '../data/content';
import { demoModel } from '../data/demo-model';
import release from '../data/demo-release.json';
import { SectionHead } from '../components/section-head/section-head';
import { ArrowRightIcon, CheckIcon, CrossIcon, FileIcon, KeyIcon } from '../components/icons/icons';
import { inlineCode } from '../lib/inline-code';
import section from './section.module.css';
import styles from './proofs.module.css';

type Proof = {
  title: string;
  body: string;
  more: { label: string; href: string };
  visual: ReactNode;
};

const PROOFS: Proof[] = [
  {
    title: 'Checked while it downloads',
    body: 'A whole-file checksum can only be compared at the end, which for a 40 GB model means finding out at the end. The signed release carries a pieces root for each file, so every piece is verified when it arrives, and a bad one is thrown away and fetched again from another source.',
    more: { label: 'How verification works', href: doc('how-it-could-work.md#verification') },
    visual: <PieceCheck />,
  },
  {
    title: 'Signed by its publisher, kept in their profile',
    body: "A release is a signed post in its publisher's own profile. The same key covers every release, so a reader can tell a known publisher from an imitator, and no hub, indexer or company can remove it from there.",
    more: { label: 'Nobody runs the list', href: doc('README.md#nobody-runs-the-list') },
    visual: <SignedRelease />,
  },
  {
    title: 'Works with the Hugging Face SDK',
    body: 'Point `HF_ENDPOINT` at the local endpoint to download with the Hugging Face SDK. Each file is verified before its first byte is returned. Compatibility with `transformers` and llama.cpp is still untested.',
    more: { label: 'The local endpoint', href: doc('cli/ENDPOINT.md') },
    visual: <SdkTerminal />,
  },
  {
    title: 'Safe formats by default',
    body: 'A signature does not make a file harmless. Formats that only hold data, such as safetensors and GGUF, download normally. Files that can run code when loaded are flagged and need a confirmation.',
    more: { label: 'Integrity is not safety', href: doc('README.md#integrity-is-not-safety') },
    visual: <FormatPolicy />,
  },
];

export function Proofs() {
  return (
    <section className={section.section} aria-labelledby='proofs-title'>
      <div className='wrap'>
        <SectionHead source='README.md#checked-while-it-downloads' id='proofs-title'>
          Any server can send the bytes. Only the publisher can sign them.
        </SectionHead>
        <div className={styles.rows}>
          {PROOFS.map((proof) => (
            <article key={proof.title} className={styles.row}>
              <div className={styles.text}>
                <h3>{proof.title}</h3>
                <p>{inlineCode(proof.body)}</p>
                <a className='link-arrow' href={proof.more.href}>
                  {proof.more.label}
                  <ArrowRightIcon size={14} />
                </a>
              </div>
              <div className={styles.visual}>{proof.visual}</div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

const short = (value: string, head = 10, tail = 6) => `${value.slice(0, head)}…${value.slice(-tail)}`;

function PieceCheck() {
  return (
    <figure className={styles.card}>
      <div className={styles.cardHead}>
        <span className={styles.file}>
          <FileIcon size={14} />
          {release.weights.path}
        </span>
        <span className={styles.dim}>{demoModel.size}</span>
      </div>
      <dl className={styles.fields}>
        <div>
          <dt>pieces root</dt>
          <dd>{short(demoModel.piecesRoot, 16, 8)}</dd>
        </div>
      </dl>
      <ol className={styles.log}>
        <li data-state='ok'>
          <span>#097</span>
          <span>peer {release.peer.split(':')[0]}</span>
          <span>
            <CheckIcon size={13} /> verified
          </span>
        </li>
        <li data-state='fault'>
          <span>#098</span>
          <span>mirror.example.org</span>
          <span>
            <CrossIcon size={13} /> hash mismatch
          </span>
        </li>
        <li data-state='note'>
          <span />
          <span>source dropped, piece requested again</span>
          <span />
        </li>
        <li data-state='ok'>
          <span>#098</span>
          <span>huggingface.co</span>
          <span>
            <CheckIcon size={13} /> verified
          </span>
        </li>
      </ol>
      <div className={styles.progress} aria-hidden='true'>
        <span style={{ width: '42%' }} />
      </div>
      <figcaption className={styles.caption}>Real file and pieces root from the signed demo; mirror.example.org is an example of a bad source.</figcaption>
    </figure>
  );
}

function SignedRelease() {
  return (
    <figure className={styles.card}>
      <div className={styles.cardHead}>
        <span className={styles.file}>
          <KeyIcon size={14} />
          Signed release
        </span>
        <span className='chip chip-verified'>{release.version}</span>
      </div>
      <dl className={styles.fields}>
        <div>
          <dt>publisher</dt>
          <dd>{release.publisher}</dd>
        </div>
        <div>
          <dt>name</dt>
          <dd>modelswarm/qwen2.5-0.5b-instruct-gguf</dd>
        </div>
        <div>
          <dt>release CID</dt>
          <dd>{release.release_cid}</dd>
        </div>
        <div>
          <dt>sha-256</dt>
          <dd>{release.weights.sha256}</dd>
        </div>
      </dl>
      <p className={styles.ok}>
        <CheckIcon size={14} />
        Checked on the reader's machine, against the publisher's key
      </p>
      <figcaption className={styles.caption}>The signed Qwen demo release, as the CLI reads it.</figcaption>
    </figure>
  );
}

function SdkTerminal() {
  return (
    <figure className={`${styles.card} ${styles.terminal}`}>
      <div className={styles.termBar}>
        <span aria-hidden='true' />
        <span aria-hidden='true' />
        <span aria-hidden='true' />
        <p>~/models</p>
      </div>
      <pre className={styles.termBody}>
        <code>
          <span className={styles.comment}># one shell: the verifying endpoint</span>
          {'\n'}
          <span className={styles.prompt}>$</span> modelswarm serve --manifest ./release.json --port 8866
          {'\n\n'}
          <span className={styles.comment}># another: your usual code</span>
          {'\n'}
          <span className={styles.prompt}>$</span> export HF_ENDPOINT=http://127.0.0.1:8866
          {'\n'}
          <span className={styles.prompt}>$</span> python
          {'\n'}
          <span className={styles.prompt}>&gt;&gt;&gt;</span> from huggingface_hub import hf_hub_download
          {'\n'}
          <span className={styles.prompt}>&gt;&gt;&gt;</span> hf_hub_download("example/model", "model.gguf")
          {'\n'}
          <span className={styles.dim}>'~/sdk-cache/…/model.gguf'</span>
        </code>
      </pre>
      <figcaption className={styles.caption}>Adapted from cli/ENDPOINT.md; example/model stands for any registered or public model.</figcaption>
    </figure>
  );
}

function FormatPolicy() {
  const rows = [
    { file: 'model.safetensors', kind: 'tensors only', ok: true },
    { file: 'model.Q4_K_M.gguf', kind: 'tensors and metadata', ok: true },
    { file: 'pytorch_model.bin', kind: 'pickle, can run code', ok: false },
  ];
  return (
    <figure className={styles.card}>
      <ul className={styles.formats}>
        {rows.map((row) => (
          <li key={row.file} data-ok={row.ok}>
            <span className={styles.file}>
              <FileIcon size={14} />
              {row.file}
            </span>
            <span className={styles.dim}>{row.kind}</span>
            <span className={styles.verdict}>
              {row.ok ? <CheckIcon size={13} /> : <CrossIcon size={13} />}
              {row.ok ? 'downloads' : 'asks first'}
            </span>
          </li>
        ))}
      </ul>
      <figcaption className={styles.caption}>The default policy; a hub can also refuse flagged formats as a posting rule.</figcaption>
    </figure>
  );
}
