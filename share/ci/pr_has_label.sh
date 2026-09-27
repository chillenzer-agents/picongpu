#!/bin/bash

set -e
set -o pipefail

# The label lives on the pull request in the repository the pipeline runs for.
# In a fork pipeline that is the fork itself (its own `pr-<n>`), so derive the
# repository from the CI environment instead of hardcoding the upstream
# repository (which would look up an unrelated PR number upstream and never see
# the label on the fork PR).
if [ -n "${GITHUB_REPOSITORY:-}" ]; then
    github_group_repo="${GITHUB_REPOSITORY}"
elif [ -n "${CI_PROJECT_PATH:-}" ]; then
    github_group_repo="${CI_PROJECT_PATH}"
else
    github_group_repo="ComputationalRadiationPhysics/picongpu"
fi

pr_id=$(echo "$CI_COMMIT_REF_NAME" | cut -d"/" -f1 | cut -d"-" -f2)
# used a token without any rights from psychocoderHPC to avoid API query limitations
curl_data=$(curl -u psychocoderHPC:$GITHUB_TOKEN -X GET https://api.github.com/repos/${github_group_repo}/pulls/${pr_id} 2>/dev/null)
if [ $? -ne 0 ] ; then
  echo "curl data\n------" >&2
  echo "$(curl -u psychocoderHPC:$GITHUB_TOKEN -X GET https://api.github.com/repos/${github_group_repo}/pulls/${pr_id})" >&2
  echo "---------" >&2
fi
# get the destination branch
all_labels=$(echo "$curl_data" | python3 -c 'import json,sys;obj=json.loads(sys.stdin.read());x = obj["labels"];labels = list(i["name"] for i in x); print(labels)')
echo "search for label: '$1'" >&2
echo "labels: '${all_labels}'" >&2
label_found=$(echo "$all_labels" | grep -q "$1" && echo 0 || echo 1)

exit $label_found
