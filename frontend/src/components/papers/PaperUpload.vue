<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'

import { isApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'

const emit = defineEmits<{
  uploaded: [paperId: string]
}>()

const uploading = ref(false)

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.warning('请上传 PDF 文件')
    return
  }
  uploading.value = true
  try {
    const res = await papersApi.uploadPaper(file)
    ElMessage.success(res.data.message)
    emit('uploaded', res.data.paper_id)
    options.onSuccess?.(res)
  } catch (error: unknown) {
    const message = isApiClientError(error) ? error.message : '上传失败'
    ElMessage.error(message)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-upload drag :http-request="handleUpload" :show-file-list="false" accept=".pdf" :disabled="uploading">
    <el-icon class="el-icon--upload"><i class="el-icon-upload" /></el-icon>
    <div class="el-upload__text">拖拽 PDF 到此处，或 <em>点击上传</em></div>
    <template #tip>
      <div class="el-upload__tip">建议 ≤32MB；上传后轮询 status 直至 ready</div>
    </template>
  </el-upload>
</template>
