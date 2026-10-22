<template>
  <!-- 第三屏：项目展示。网格整齐，详情走 Dialog 而非卡片内展开 -->
  <section class="home-section projects-section" id="section-projects">
    <div class="projects-inner">
      <h2 class="projects-title">PROJECTS</h2>

      <div class="projects-grid">
        <article
          v-for="(item, i) in projects"
          :key="`project-${i}`"
          class="project-card"
          @click="onCardClick(item)"
        >
          <img
            class="project-cover"
            :src="item.img"
            :alt="item.title"
            :style="{ '--project-item-brightness': `${effectiveBrightness(item)}%` }"
            loading="lazy"
          />
          <div class="project-overlay"></div>
          <div class="project-meta">
            <div class="project-name">{{ item.title }}</div>
            <div class="project-sub">
              <span class="project-sub-text">{{ item.subtitle }}</span>
              <span class="project-arrow" :class="{ 'is-empty': !item.url && !item.to }">
                {{ item.url ? '↗' : (item.to ? '→' : '·') }}
              </span>
            </div>
            <div v-if="!item.url && !item.to" class="project-soon">Coming soon</div>
          </div>
        </article>
      </div>

      <!-- 声明区：备案号与版权统一固定在第三屏左下角，按 config.statement 的顺序展示。
           必须留在 .projects-inner 内部：桌面端它是绝对定位（相对 .projects-section），
           移动端改回 static 时才会落在内容列里；放到 inner 外面会变成 section(flex) 的兄弟项被挤到旁边。 -->
      <footer v-if="statements.length" class="site-footer">
        <template v-for="(item, i) in statements" :key="`statement-${i}`">
          <a
            v-if="isIcp(item)"
            class="footer-icp"
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noopener noreferrer"
          >{{ item }}</a>
          <span v-else class="footer-text">{{ item }}</span>
        </template>
      </footer>
    </div>

    <!-- 项目详情 Dialog：避免展开造成网格跳动 -->
    <v-dialog v-model="detailOpen" max-width="560">
      <v-card class="detail-card">
        <div class="detail-head">
          <div>
            <div class="detail-title">{{ activeProject?.title }}</div>
            <div class="detail-sub">{{ activeProject?.subtitle }}</div>
          </div>
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailOpen = false"></v-btn>
        </div>
        <div class="detail-text">{{ activeProject?.text }}</div>
        <div v-if="activeProject?.url" class="detail-foot">
          <v-btn
            variant="tonal"
            :href="activeProject.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            前往项目
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </section>
</template>

<script>
export default {
  name: 'ProjectsSection',
  props: {
    projects: { type: Array, default: () => [] },
    statements: { type: Array, default: () => [] },
    globalCardBrightness: { type: Number, default: 100 },
  },
  data() {
    return {
      detailOpen: false,
      activeProject: null,
    };
  },
  methods: {
    effectiveBrightness(item) {
      const globalValue = Math.min(140, Math.max(60, Number(this.globalCardBrightness) || 100));
      const itemValue = Math.min(140, Math.max(60, Number(item?.brightness ?? 140)));
      return Math.min(globalValue, itemValue);
    },
    isIcp(item) {
      return typeof item === 'string' && item.includes('ICP备');
    },
    onCardClick(item) {
      if (!item) return;
      // 三种点击行为，优先级：站内子页面 → 外部链接 → 详情弹窗
      // 1) to：站内路由（如 camera 卡片的 "/camera"）
      if (item.to) {
        this.$router.push(item.to);
        return;
      }
      // 2) url：外部链接，新标签打开
      if (item.url) {
        window.open(item.url, '_blank', 'noopener,noreferrer');
        return;
      }
      // 3) 两者都空：打开详情，绝不 window.open('')
      this.activeProject = item;
      this.detailOpen = true;
    },
  },
};
</script>

<style scoped>
.projects-section {
  position: relative;
}

.projects-inner {
  width: min(1300px, calc(100vw - 96px));
}

.projects-title {
  margin: 0 0 32px;
  text-align: center;
  font-family: "myfont";
  font-weight: 400;
  font-size: clamp(28px, 3vw, 44px);
  letter-spacing: 0.16em;
  color: var(--leleo-welcomtitle-color);
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
}

.project-card {
  position: relative;
  height: 242px;
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.16);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.16);
  transition: transform 250ms ease, border-color 250ms ease, box-shadow 250ms ease;
  animation: cardIn 520ms cubic-bezier(0.22, 0.61, 0.36, 1) both;
}

.project-card:nth-child(2) {
  animation-delay: 70ms;
}
.project-card:nth-child(3) {
  animation-delay: 140ms;
}
.project-card:nth-child(4) {
  animation-delay: 210ms;
}

@keyframes cardIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .project-card {
    animation: none;
  }
}

.project-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: brightness(var(--project-item-brightness, var(--leleo-project-card-brightness, 100%)));
  transition: transform 250ms ease, filter 250ms ease;
}

.project-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(31, 61, 82, 0.22) 0%,
    rgba(20, 48, 68, 0.34) 56%,
    rgba(7, 28, 42, 0.88) 100%
  );
  opacity: var(--leleo-project-overlay-opacity, .60);
}

/* 声明区（备案号 + 版权）固定在第三屏左下角。
   壁纸明亮时纯白小字等于隐身（与设置齿轮同一教训），所以给一层柔和深色底 + 文字阴影。 */
.site-footer {
  position: absolute;
  left: clamp(18px, 3vw, 48px);
  bottom: max(16px, env(safe-area-inset-bottom));
  z-index: 3;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 6px;
  max-width: calc(100% - 2 * clamp(18px, 3vw, 48px));
  margin: 0;
  padding: 8px 15px;
  border-radius: 999px;
  background: rgba(8, 20, 32, 0.46);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
  color: rgba(255, 255, 255, 0.94);
  font-size: 0.72rem;
  line-height: 1.4;
  letter-spacing: 0.03em;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.site-footer > * + *::before {
  content: '·';
  margin-right: 6px;
  opacity: 0.45;
}

.footer-icp {
  color: inherit;
  text-decoration: none;
  transition: color 200ms ease;
}

.footer-icp:hover {
  color: #ffffff;
  text-decoration: underline;
}

.footer-text {
  color: inherit;
}

.project-meta {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 14px;
  color: rgba(255, 255, 255, 0.96);
}

.project-name {
  font-size: 1.15rem;
  font-weight: 600;
  line-height: 1.2;
}

.project-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}

.project-sub-text {
  font-size: 0.82rem;
  opacity: 0.82;
}

.project-arrow {
  font-size: 0.82rem;
  opacity: 0.9;
  transition: transform 250ms ease;
}

.project-arrow.is-empty {
  opacity: 0.5;
}

.project-soon {
  margin-top: 4px;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  opacity: 0.62;
}

/* 桌面 hover：位移 + 轻微放大 + 边框提亮，不做翻转/3D/霓虹 */
@media (hover: hover) {
  .project-card:hover {
    transform: translateY(-4px);
    border-color: rgba(255, 255, 255, 0.34);
    box-shadow: 0 20px 46px rgba(0, 0, 0, 0.24);
  }
  .project-card:hover .project-cover {
    transform: scale(1.025);
  }
  .project-card:hover .project-arrow {
    transform: translate(2px, -2px);
  }
}

/* ---------- 详情 Dialog ---------- */
.detail-card {
  padding: 18px 20px 20px;
  border-radius: 16px;
  background: rgba(15, 45, 70, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(var(--leleo-blur));
  -webkit-backdrop-filter: blur(var(--leleo-blur));
  color: var(--leleo-vcard-color);
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-title {
  font-size: 1.1rem;
  font-weight: 600;
}

.detail-sub {
  margin-top: 2px;
  font-size: 0.82rem;
  opacity: 0.72;
}

.detail-text {
  margin-top: 14px;
  font-size: 0.92rem;
  line-height: 1.65;
  opacity: 0.9;
}

.detail-foot {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}

/* ---------- 响应式 ---------- */
@media (max-width: 1280px) {
  .projects-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .projects-inner {
    width: 100%;
    padding: 0 24px;
  }
  .projects-title {
    margin-bottom: 22px;
  }
  .projects-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  .project-card {
    height: 210px;
  }
  /* 移动端卡片纵向堆叠后 section 会被撑高，固定定位会与卡片重叠 —— 改为跟随内容流。
     .projects-inner 在移动端已有 24px 内边距，这里只留上边距即可与卡片对齐。 */
  .site-footer {
    position: static;
    display: flex;
    width: fit-content;
    max-width: 100%;
    margin: 16px 0 0;
    border-radius: 14px;
    font-size: 0.68rem;
  }
}
</style>
