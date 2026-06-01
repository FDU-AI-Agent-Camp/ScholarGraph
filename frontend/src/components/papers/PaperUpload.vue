<script setup lang="ts">
import { ref } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'

import { isApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'

const UPLOAD_MAIN_COPY = '拖拽 PDF 到此处，或'
const UPLOAD_CLICK_LABEL = '点击上传'
const UPLOAD_TIP = '建议 ≤32MB · 上传后自动进入解构流水线'
const UPLOADING_LABEL = '上传中…'

const emit = defineEmits<{
  uploaded: [paperId: string]
}>()

const uploading = ref(false)
const uploadingFileName = ref('')
const uploadError = ref('')

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.warning('请上传 PDF 文件')
    return
  }

  uploadError.value = ''
  uploading.value = true
  uploadingFileName.value = file.name

  try {
    const res = await papersApi.uploadPaper(file)
    ElMessage.success(res.data.message)
    emit('uploaded', res.data.paper_id)
    options.onSuccess?.(res)
  } catch (error: unknown) {
    const message = isApiClientError(error) ? error.message : '上传失败，请稍后重试'
    uploadError.value = message
  } finally {
    uploading.value = false
    uploadingFileName.value = ''
  }
}
</script>

<template>
  <div class="paper-upload">
    <el-alert
      v-if="uploadError"
      class="paper-upload__error"
      type="error"
      :title="uploadError"
      show-icon
      :closable="true"
      @close="uploadError = ''"
    />
    <el-upload
      drag
      class="paper-upload__dropzone"
      :http-request="handleUpload"
      :show-file-list="false"
      accept=".pdf"
      :disabled="uploading"
    >
      <div v-if="uploading" class="paper-upload__uploading">
        <el-progress :percentage="100" :indeterminate="true" :show-text="false" />
        <p class="paper-upload__filename text-mono">{{ uploadingFileName }}</p>
        <p class="paper-upload__status text-body">{{ UPLOADING_LABEL }}</p>
      </div>
      <template v-else>
        <el-icon class="paper-upload__icon" aria-hidden="true"><Upload /></el-icon>
        <p class="paper-upload__text text-body">
          {{ UPLOAD_MAIN_COPY }}
          <em>{{ UPLOAD_CLICK_LABEL }}</em>
        </p>
      </template>
    </el-upload>
    <p class="paper-upload__tip text-caption">{{ UPLOAD_TIP }}</p>
  </div>
</template>

<style scoped>
.paper-upload__error {
  margin-bottom: var(--spacing-12);
}

.paper-upload__dropzone {
  width: 100%;
}

.paper-upload__dropzone :deep(.el-upload) {
  width: 100%;
}

.paper-upload__dropzone :deep(.el-upload-dragger) {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 160px;
  padding: var(--spacing-24);
  border: 2px dashed var(--color-border-strong);
  border-radius: var(--radius-xl);
  background: var(--color-bg-subtle);
  transition:
    background var(--transition-instant),
    border-color var(--transition-instant);
}

.paper-upload__dropzone :deep(.el-upload-dragger:hover),
.paper-upload__dropzone :deep(.el-upload-dragger.is-dragover) {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.paper-upload__icon {
  font-size: var(--spacing-48);
  color: var(--color-text-muted);
}

.paper-upload__text {
  margin: var(--spacing-12) 0 0;
  color: var(--color-text-primary);
}

.paper-upload__text em {
  font-style: normal;
  font-weight: 600;
  color: var(--color-primary);
}

.paper-upload__tip {
  margin: var(--spacing-8) 0 0;
}

.paper-upload__uploading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-8);
  width: min(320px, 100%);
}

.paper-upload__filename {
  margin: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
}

.paper-upload__status {
  margin: 0;
  color: var(--color-text-primary);
}
</style>
