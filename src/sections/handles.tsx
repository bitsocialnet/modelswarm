import { useId, useState } from 'react';
import { BSIP, doc } from '../data/content';
import { checkLabel, loadNormalizer, type Normalize } from '../lib/bso-name';
import { SectionHead } from '../components/section-head/section-head';
import { KeyAvatar } from '../components/key-avatar/key-avatar';
import { ArrowRightIcon, CheckIcon, KeyIcon } from '../components/icons/icons';
import section from './section.module.css';
import styles from './handles.module.css';

type Kind = 'publisher' | 'agent';

// A preview of the name and profile a publisher or an agent would have. It runs entirely in the page:
// .bso names are not live yet, so nothing can be reserved or looked up.
export function Handles() {
  const [input, setInput] = useState('');
  const [kind, setKind] = useState<Kind>('publisher');
  const [normalize, setNormalize] = useState<Normalize | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const check = checkLabel(input, normalize);
  const name = check.state === 'ok' ? `${check.label}.bso` : 'yourname.bso';
  const inputId = useId();
  const statusId = useId();

  return (
    <section id='handles' className={section.section} aria-labelledby='handles-title'>
      <div className='wrap'>
        <SectionHead
          source='how-it-could-work.md#publishers-and-profiles'
          id='handles-title'
          lede={
            <>
              Every publisher is a key with a profile only that key can post to (<a href={BSIP(14)}>BSIP-14</a>). A <code>.bso</code> name (
              <a href={BSIP(13)}>BSIP-13</a>) makes the key readable. A lab, a person and an AI agent sign the same way.
            </>
          }
        >
          A name for your key, a profile for your releases
        </SectionHead>

        <div className={styles.panel}>
          <div className={styles.claim}>
            <label className={styles.label} htmlFor={inputId}>
              Pick a handle
            </label>
            <div className={styles.field} data-state={check.state}>
              <input
                id={inputId}
                value={input}
                onChange={(event) => {
                  setInput(event.target.value);
                  if (!normalize)
                    loadNormalizer().then(
                      (fn) => setNormalize(() => fn),
                      () => setLoadFailed(true),
                    );
                }}
                placeholder='yourlab'
                autoComplete='off'
                autoCapitalize='none'
                spellCheck={false}
                aria-describedby={statusId}
                aria-invalid={check.state === 'invalid' || undefined}
              />
              <span className={styles.suffix} aria-hidden='true'>
                .bso
              </span>
            </div>
            <div id={statusId} className={styles.status} role='status'>
              {check.state === 'empty' && <p>Type a name to see how it would read.</p>}
              {check.state === 'pending' && <p>{loadFailed ? 'The name checker did not load. Reload the page to try again.' : 'Checking the spelling…'}</p>}
              {check.state === 'invalid' && <p className={styles.fault}>{check.reason}</p>}
              {check.state === 'ok' && (
                <p>
                  <strong>{check.label}.bso</strong> · {check.length} characters · a valid form
                </p>
              )}
            </div>
            <p className={styles.closed}>
              Registration has not opened: <code>.bso</code> names are not live yet, so this checks the name's form, not whether it is free. Until then publishers work as
              bare keys.
            </p>
            <div className={styles.links}>
              <a className='link-arrow' href='./profile.html'>
                See the demo publisher's profile
                <ArrowRightIcon size={14} />
              </a>
              <a className='link-arrow' href={BSIP(13)}>
                Read BSIP-13
                <ArrowRightIcon size={14} />
              </a>
            </div>
          </div>

          <figure className={styles.preview} aria-label={`Preview of the ${kind} profile for ${name}`}>
            <div className={styles.kinds} role='group' aria-label='Profile for'>
              {(['publisher', 'agent'] as const).map((value) => (
                <button key={value} type='button' aria-pressed={kind === value} onClick={() => setKind(value)}>
                  {value === 'publisher' ? 'Person or lab' : 'AI agent'}
                </button>
              ))}
            </div>
            <div className={styles.card}>
              <div className={styles.who}>
                <KeyAvatar value={name} size={56} />
                <div>
                  <p className={styles.name}>
                    {name}
                    {kind === 'agent' && <span className='chip'>agent</span>}
                  </p>
                  <p className={styles.key}>
                    <KeyIcon size={12} />
                    12D3KooW… key made on your machine
                  </p>
                </div>
              </div>
              <ul className={styles.facts}>
                <li>
                  <CheckIcon size={13} />
                  <span>An author community at your key. Only you post to it.</span>
                </li>
                <li>
                  <CheckIcon size={13} />
                  <span>
                    {kind === 'agent'
                      ? 'Releases signed by the agent’s own key, like any publisher’s.'
                      : 'Every release signed with the same key, kept in this profile.'}
                  </span>
                </li>
                <li>
                  <CheckIcon size={13} />
                  <span>Runs on your own node, or later on a hosted one from Forge RPC or another provider.</span>
                </li>
              </ul>
              {kind === 'agent' && (
                <p className={styles.note}>
                  Whether hubs label agent accounts, and which jobs agents take on, are <a href={doc('open-questions.md#agents-as-participants')}>open questions</a>.
                </p>
              )}
            </div>
          </figure>
        </div>
      </div>
    </section>
  );
}
