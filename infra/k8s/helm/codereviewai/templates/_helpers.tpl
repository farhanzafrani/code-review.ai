{{- define "codereviewai.labels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: codereviewai
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "codereviewai.selectorLabels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
