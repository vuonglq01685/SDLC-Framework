// Story 5.12 RED witness: client-side routing via history.replaceState.
function navigate(path) {
  history.replaceState({}, "", path);
}
