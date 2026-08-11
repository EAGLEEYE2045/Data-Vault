"""
CloudVault UI -- Streamlit front-end over the existing pipeline.

Run with:
    export DISCORD_WEBHOOK_URL="..."
    streamlit run app.py
"""

import streamlit as st
from datetime import datetime

from pipeline import CloudVault

st.set_page_config(page_title="CloudVault", page_icon="🗄️", layout="centered")


@st.cache_resource
def get_vault() -> CloudVault:
    return CloudVault()


st.title("🗄️ CloudVault")
st.caption("Encrypted file storage, backed by Discord")

try:
    vault = get_vault()
except ValueError as e:
    st.error(str(e))
    st.info("Set DISCORD_WEBHOOK_URL as an environment variable, then restart Streamlit.")
    st.stop()

# ---------- Upload ----------
st.subheader("Upload")
uploaded = st.file_uploader("Choose a file", accept_multiple_files=True)

if uploaded and st.button("Upload to CloudVault", type="primary"):
    progress = st.progress(0.0)
    for i, f in enumerate(uploaded):
        dest = vault.upload_bytes(f.name, f.getvalue())
        progress.progress((i + 1) / len(uploaded))
    st.success(f"Processed {len(uploaded)} file(s)")
    st.rerun()

st.divider()

# ---------- File list ----------
st.subheader("Files")
rows = vault.manifest.list_files()

if not rows:
    st.info("No files uploaded yet.")
else:
    for file_id, filename, size, created_at in rows:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"**{filename}**")
            when = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
            st.caption(f"{size:,} bytes • {when}")
        with col2:
            data = st.session_state.get(f"dl_{file_id}")
            if st.button("Fetch", key=f"fetch_{file_id}"):
                with st.spinner("Decrypting..."):
                    st.session_state[f"dl_{file_id}"] = vault.get_bytes(file_id)
                st.rerun()
            if data is not None:
                st.download_button(
                    "Save",
                    data=data,
                    file_name=filename,
                    key=f"save_{file_id}",
                )
        with col3:
            if st.button("Delete", key=f"del_{file_id}"):
                vault.backend.delete(vault.manifest.get(file_id).ref)
                vault.manifest.delete(file_id)
                st.rerun()

st.divider()

# ---------- Verify ----------
st.subheader("Verify")
st.caption("Confirms every manifest entry is still retrievable from Discord.")

if st.button("Run verification"):
    with st.spinner("Checking Discord..."):
        missing = vault.check_missing()
    st.session_state["missing"] = missing
    total = len(vault.manifest.list_files())
    if not missing:
        st.success(f"All {total} files confirmed on Discord.")
    else:
        st.warning(f"{len(missing)} of {total} files are missing from Discord.")

missing = st.session_state.get("missing")
if missing:
    for file_id, filename in missing:
        st.write(f"- {filename} (`{file_id}`)")
    if st.button("Prune missing entries from manifest", type="secondary"):
        vault.prune_ids([fid for fid, _ in missing])
        st.session_state["missing"] = None
        st.success("Pruned.")
        st.rerun()