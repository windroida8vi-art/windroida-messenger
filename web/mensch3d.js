'use strict';
/* A tiny WebGL engine for the Mensch board (no library, no internet needed): a lit 3D board with the SVG board as its top texture,
   lathe-turned pawns that hop from cell to cell, soft shadows, a tumbling 3D die. Everything here is optional: when WebGL is not
   available mensch.js simply keeps drawing the flat SVG board. */
const M4={
  ident:()=>new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]),
  mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+r]*b[c*4+k];o[c*4+r]=s}return o},
  persp(fy,asp,n,f){const t=1/Math.tan(fy/2),o=new Float32Array(16);o[0]=t/asp;o[5]=t;o[10]=(f+n)/(n-f);o[11]=-1;o[14]=2*f*n/(n-f);return o},
  look(e,c,u){let zx=e[0]-c[0],zy=e[1]-c[1],zz=e[2]-c[2];let l=Math.hypot(zx,zy,zz);zx/=l;zy/=l;zz/=l;
    let xx=u[1]*zz-u[2]*zy,xy=u[2]*zx-u[0]*zz,xz=u[0]*zy-u[1]*zx;l=Math.hypot(xx,xy,xz);xx/=l;xy/=l;xz/=l;
    const yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;
    return new Float32Array([xx,yx,zx,0,xy,yy,zy,0,xz,yz,zz,0,-(xx*e[0]+xy*e[1]+xz*e[2]),-(yx*e[0]+yy*e[1]+yz*e[2]),-(zx*e[0]+zy*e[1]+zz*e[2]),1])},
  model(x,y,z,ry,s){const c=Math.cos(ry),n=Math.sin(ry);return new Float32Array([c*s,0,-n*s,0,0,s,0,0,n*s,0,c*s,0,x,y,z,1])},
  fromQuat(q,s,x,y,z){const[a,b,c,d]=q,o=M4.ident();
    o[0]=(1-2*(c*c+d*d))*s;o[1]=2*(b*c+a*d)*s;o[2]=2*(b*d-a*c)*s;o[4]=2*(b*c-a*d)*s;o[5]=(1-2*(b*b+d*d))*s;o[6]=2*(c*d+a*b)*s;
    o[8]=2*(b*d+a*c)*s;o[9]=2*(c*d-a*b)*s;o[10]=(1-2*(b*b+c*c))*s;o[12]=x;o[13]=y;o[14]=z;return o}};
const Q={ // quaternions [w,x,y,z]
  axis(ax,ay,az,a){const l=Math.hypot(ax,ay,az)||1,s=Math.sin(a/2)/l;return[Math.cos(a/2),ax*s,ay*s,az*s]},
  mul(p,q){return[p[0]*q[0]-p[1]*q[1]-p[2]*q[2]-p[3]*q[3],p[0]*q[1]+p[1]*q[0]+p[2]*q[3]-p[3]*q[2],p[0]*q[2]-p[1]*q[3]+p[2]*q[0]+p[3]*q[1],p[0]*q[3]+p[1]*q[2]-p[2]*q[1]+p[3]*q[0]]},
  norm(q){const l=Math.hypot(...q)||1;return q.map(v=>v/l)},
  slerp(a,b,t){let d=a[0]*b[0]+a[1]*b[1]+a[2]*b[2]+a[3]*b[3];if(d<0){b=b.map(v=>-v);d=-d}
    if(d>.9995)return Q.norm(a.map((v,i)=>v+(b[i]-v)*t));const th=Math.acos(d),s=Math.sin(th),w1=Math.sin((1-t)*th)/s,w2=Math.sin(t*th)/s;return a.map((v,i)=>v*w1+b[i]*w2)}};

const VS='attribute vec3 aPos;attribute vec3 aNor;attribute vec2 aUv;uniform mat4 uVP;uniform mat4 uModel;varying vec3 vN;varying vec3 vW;varying vec2 vUv;'+
  'void main(){vec4 w=uModel*vec4(aPos,1.0);vW=w.xyz;vN=mat3(uModel)*aNor;vUv=aUv;gl_Position=uVP*w;}';
const FS='precision mediump float;uniform vec3 uColor;uniform vec3 uCam;uniform float uShin;uniform float uSpec;uniform sampler2D uTex;uniform float uUseTex;uniform float uGlow;uniform float uAlpha;uniform float uBlob;'+
  'varying vec3 vN;varying vec3 vW;varying vec2 vUv;'+
  'void main(){if(uBlob>0.5){float a=smoothstep(0.5,0.05,length(vUv-0.5))*uAlpha;gl_FragColor=vec4(0.0,0.0,0.0,a);return;}'+
  'vec3 n=normalize(vN);vec3 L=normalize(vec3(-0.45,1.0,0.65));vec3 V=normalize(uCam-vW);'+
  'vec3 base=uUseTex>0.5?texture2D(uTex,vUv).rgb:uColor;float diff=max(dot(n,L),0.0);float hemi=0.5+0.5*n.y;'+
  'vec3 col=base*(0.52+0.30*hemi+0.55*diff);vec3 H=normalize(L+V);float sp=pow(max(dot(n,H),0.0),uShin)*uSpec;'+
  'col+=vec3(sp)+uGlow*vec3(1.0,0.85,0.3)*(0.45+0.55*n.y);gl_FragColor=vec4(col,1.0);}';

/* ---- geometry builders: {p:[],n:[],u:[],i:[]} ---- */
function gBox(w,h,d,y0){const hw=w/2,hd=d/2,y1=y0+h,P=[],N=[],U=[],I=[];
  const face=(a,b,c,d2,nx,ny,nz)=>{const o=P.length/3;P.push(...a,...b,...c,...d2);for(let k=0;k<4;k++)N.push(nx,ny,nz);U.push(0,0,1,0,1,1,0,1);I.push(o,o+1,o+2,o,o+2,o+3)};
  face([-hw,y1,hd],[hw,y1,hd],[hw,y1,-hd],[-hw,y1,-hd],0,1,0);face([-hw,y0,-hd],[hw,y0,-hd],[hw,y0,hd],[-hw,y0,hd],0,-1,0);
  face([-hw,y0,hd],[hw,y0,hd],[hw,y1,hd],[-hw,y1,hd],0,0,1);face([hw,y0,-hd],[-hw,y0,-hd],[-hw,y1,-hd],[hw,y1,-hd],0,0,-1);
  face([hw,y0,hd],[hw,y0,-hd],[hw,y1,-hd],[hw,y1,hd],1,0,0);face([-hw,y0,-hd],[-hw,y0,hd],[-hw,y1,hd],[-hw,y1,-hd],-1,0,0);
  return{p:P,n:N,u:U,i:I}}
function gQuad(w,d,y,uvOn){const hw=w/2,hd=d/2;return{p:[-hw,y,hd,hw,y,hd,hw,y,-hd,-hw,y,-hd],n:[0,1,0,0,1,0,0,1,0,0,1,0],u:uvOn?[0,1,1,1,1,0,0,0]:[0,1,1,1,1,0,0,0],i:[0,1,2,0,2,3]}}
function gLathe(prof,seg){ // prof: [[r,y],...] bottom -> top
  const P=[],N=[],U=[],I=[],m=prof.length;
  const nor=k=>{const a=prof[Math.max(0,k-1)],b=prof[Math.min(m-1,k+1)];let dr=b[0]-a[0],dy=b[1]-a[1];const l=Math.hypot(dr,dy)||1;return[dy/l,-dr/l]}; // outward normal (r,y)
  for(let s=0;s<=seg;s++){const a=s/seg*Math.PI*2,c=Math.cos(a),sn=Math.sin(a);
    for(let k=0;k<m;k++){const[nr,ny]=nor(k);P.push(prof[k][0]*c,prof[k][1],prof[k][0]*sn);N.push(nr*c,ny,nr*sn);U.push(s/seg,k/(m-1))}}
  for(let s=0;s<seg;s++)for(let k=0;k<m-1;k++){const a=s*m+k,b=(s+1)*m+k;I.push(a,b,a+1,b,b+1,a+1)}
  return{p:P,n:N,u:U,i:I}}
function gMerge(list){const o={p:[],n:[],u:[],i:[]};for(const g of list){const b=o.p.length/3;o.p.push(...g.p);o.n.push(...g.n);o.u.push(...g.u);for(const k of g.i)o.i.push(k+b)}return o}
function gMove(g,x,y,z){const p=g.p.slice();for(let k=0;k<p.length;k+=3){p[k]+=x;p[k+1]+=y;p[k+2]+=z}return{p,n:g.n,u:g.u,i:g.i}}
function gDisc(r,seg,nx,ny,nz,cx,cy,cz,ux,uy,uz,vx,vy,vz,lift){ // flat disc (a die pip) lying on a face
  const P=[cx+nx*lift,cy+ny*lift,cz+nz*lift],N=[nx,ny,nz],U=[.5,.5],I=[];
  for(let s=0;s<=seg;s++){const a=s/seg*Math.PI*2,c=Math.cos(a)*r,sn=Math.sin(a)*r;P.push(cx+ux*c+vx*sn+nx*lift,cy+uy*c+vy*sn+ny*lift,cz+uz*c+vz*sn+nz*lift);N.push(nx,ny,nz);U.push(.5,.5)}
  for(let s=0;s<seg;s++)I.push(0,s+1,s+2);return{p:P,n:N,u:U,i:I}}

/* ---- a small GL context wrapper ---- */
class GL3{
  constructor(canvas){
    const gl=canvas.getContext('webgl',{antialias:true,alpha:true,premultipliedAlpha:false})||canvas.getContext('experimental-webgl');
    if(!gl)throw new Error('no webgl');this.gl=gl;this.canvas=canvas;
    const sh=(t,src)=>{const s=gl.createShader(t);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s};
    const pr=this.pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,FS));gl.linkProgram(pr);
    if(!gl.getProgramParameter(pr,gl.LINK_STATUS))throw new Error('link');gl.useProgram(pr);
    this.loc={};for(const n of['uVP','uModel','uColor','uCam','uShin','uSpec','uTex','uUseTex','uGlow','uAlpha','uBlob'])this.loc[n]=gl.getUniformLocation(pr,n);
    this.at={pos:gl.getAttribLocation(pr,'aPos'),nor:gl.getAttribLocation(pr,'aNor'),uv:gl.getAttribLocation(pr,'aUv')};
    gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);gl.cullFace(gl.BACK);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    this.lost=false;canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.lost=true});
  }
  mesh(g){const gl=this.gl,mk=(t,a,tp)=>{const b=gl.createBuffer();gl.bindBuffer(t,b);gl.bufferData(t,a,gl.STATIC_DRAW);return b};
    return{pos:mk(gl.ARRAY_BUFFER,new Float32Array(g.p)),nor:mk(gl.ARRAY_BUFFER,new Float32Array(g.n)),uv:mk(gl.ARRAY_BUFFER,new Float32Array(g.u)),
      idx:mk(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(g.i)),n:g.i.length}}
  tex(canvasOrImg){const gl=this.gl,t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,canvasOrImg);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return t}
  frame(w,h,clear){const gl=this.gl;gl.viewport(0,0,w,h);gl.clearColor(clear[0],clear[1],clear[2],clear[3]);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT)}
  draw(m,model,vp,cam,o){const gl=this.gl,L=this.loc;
    gl.bindBuffer(gl.ARRAY_BUFFER,m.pos);gl.enableVertexAttribArray(this.at.pos);gl.vertexAttribPointer(this.at.pos,3,gl.FLOAT,false,0,0);
    gl.bindBuffer(gl.ARRAY_BUFFER,m.nor);gl.enableVertexAttribArray(this.at.nor);gl.vertexAttribPointer(this.at.nor,3,gl.FLOAT,false,0,0);
    gl.bindBuffer(gl.ARRAY_BUFFER,m.uv);gl.enableVertexAttribArray(this.at.uv);gl.vertexAttribPointer(this.at.uv,2,gl.FLOAT,false,0,0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,m.idx);
    gl.uniformMatrix4fv(L.uVP,false,vp);gl.uniformMatrix4fv(L.uModel,false,model);gl.uniform3fv(L.uCam,cam);
    const c=o.color||[1,1,1];gl.uniform3f(L.uColor,c[0],c[1],c[2]);gl.uniform1f(L.uShin,o.shin||24);gl.uniform1f(L.uSpec,o.spec||0);
    gl.uniform1f(L.uGlow,o.glow||0);gl.uniform1f(L.uAlpha,o.alpha==null?1:o.alpha);gl.uniform1f(L.uBlob,o.blob?1:0);
    if(o.tex){gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,o.tex);gl.uniform1i(L.uTex,0);gl.uniform1f(L.uUseTex,1)}else gl.uniform1f(L.uUseTex,0);
    gl.drawElements(gl.TRIANGLES,m.n,gl.UNSIGNED_SHORT,0)}
}
const hex3=h=>[parseInt(h.slice(1,3),16)/255,parseInt(h.slice(3,5),16)/255,parseInt(h.slice(5,7),16)/255];

/* ---- the board scene ---- */
const MN3={ok:null,on:(()=>{try{return localStorage.getItem('wd-mn-3d')!=='0'}catch{return true}})(),
  canvas:null,g:null,key:'',pawns:{},legal:new Set(),yaw:0,raf:0,dirty:true,tex:null,onPick:null,w:0,h:0,t0:performance.now()};
MN3.supported=function(){
  if(MN3.ok!==null)return MN3.ok;
  try{const c=document.createElement('canvas'),g=c.getContext('webgl')||c.getContext('experimental-webgl');MN3.ok=!!g}catch{MN3.ok=false}
  return MN3.ok};
MN3.build=function(v,baseSvg,seat){
  const key=v.players.map(p=>p.id+':'+p.seat).join('|')+'#'+seat;
  if(MN3.canvas&&MN3.key===key&&!MN3.g.lost)return MN3.canvas;
  MN3.destroy();
  const cv=document.createElement('canvas');cv.className='mn3d';cv.style.touchAction='manipulation';
  try{MN3.g=new GL3(cv)}catch{MN3.ok=false;MN3.g=null;return null}
  const g=MN3.g;MN3.canvas=cv;MN3.key=key;MN3.pawns={};MN3.yaw=[90,180,270,0][seat==null?3:seat]*Math.PI/180;
  // static meshes
  MN3.mBase=g.mesh(gBox(16.2,.7,16.2,-.72));
  MN3.mTop=g.mesh(gQuad(15,15,0,true));
  MN3.mFrame=g.mesh(gBox(15.6,.12,15.6,-.14));
  const prof=[[0,0],[.44,0],[.46,.05],[.42,.12],[.3,.2],[.2,.36],[.16,.52],[.2,.58],[.3,.62],[.3,.66],[.2,.7]];
  const head=[];for(let k=0;k<=10;k++){const a=k/10*Math.PI;head.push([Math.sin(a)*.24,.84+Math.cos(a)*-.24+.24-.0])}
  MN3.mPawn=g.mesh(gMerge([gLathe(prof,22),gLathe(head.map(p=>[p[0],p[1]+.02]),20)]));
  MN3.mBlob=g.mesh(gQuad(1.5,1.5,0,true));
  // the flat board drawing becomes the texture of the top
  if(baseSvg){const s=baseSvg.cloneNode(true);s.setAttribute('width','1024');s.setAttribute('height','1024');
    const img=new Image();img.onload=()=>{try{const c2=document.createElement('canvas');c2.width=c2.height=1024;const x=c2.getContext('2d');x.drawImage(img,0,0,1024,1024);
      if(MN3.g===g&&!g.lost){MN3.tex=g.tex(c2);MN3.dirty=true;MN3.kick()}}catch{}};
    img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(s))}
  MN3.tex=null;
  for(const p of v.players){if(p.seat==null)continue;for(let i=0;i<4;i++){
    MN3.pawns[p.id+':'+i]={u:p.id,i,col:hex3(MNCOL[MNCOLS[p.seat]]),x:0,z:0,y:0,tx:0,tz:0,fx:0,fz:0,t0:0,dur:0,hop:0,s:1,sT:1,vis:true,init:false}}}
  // tapping a glowing pawn
  cv.addEventListener('click',e=>{
    const r=cv.getBoundingClientRect(),nx=((e.clientX-r.left)/r.width)*2-1,ny=-(((e.clientY-r.top)/r.height)*2-1);
    const hit=MN3.pick(nx,ny);if(hit!=null&&MN3.onPick)MN3.onPick(hit)});
  MN3.kick();return cv};
MN3.destroy=function(){cancelAnimationFrame(MN3.raf);MN3.raf=0;MN3.canvas=null;MN3.g=null;MN3.tex=null;MN3.key='';MN3.pawns={}};
/* world position of grid point (gx,gy) after the board turned so that MY yard is at the bottom-left */
MN3.world=function(gx,gy){const x=gx-7.5,z=gy-7.5,c=Math.cos(MN3.yaw),s=Math.sin(MN3.yaw);return[x*c+z*s,-x*s+z*c]};
MN3.place=function(spots,now){ // spots: [{u,i,x,y,pos,n}]  grid coordinates (15x15 units)
  now=now||performance.now();
  for(const sp of spots){const P=MN3.pawns[sp.u+':'+sp.i];if(!P)continue;const[wx,wz]=MN3.world(sp.x,sp.y);
    const sc=sp.n>1&&sp.pos>=0?.8:1;
    if(!P.init){P.x=P.tx=wx;P.z=P.tz=wz;P.init=true;P.s=P.sT=sc;continue}
    if(Math.abs(wx-P.tx)>.01||Math.abs(wz-P.tz)>.01){
      const dist=Math.hypot(wx-P.x,wz-P.z);P.fx=P.x;P.fz=P.z;P.tx=wx;P.tz=wz;P.t0=now;P.dur=dist>2.5?420:150;P.hop=dist>2.5?1.6:.55;MN3.kick()}
    P.sT=sc;P.vis=true}
  MN3.dirty=true;MN3.kick()};
MN3.setLegal=function(keys){MN3.legal=new Set(keys);MN3.dirty=true;MN3.kick()};
MN3.hit=function(u,i){const P=MN3.pawns[u+':'+i];if(P){P.sT=0;P.hitAt=performance.now();MN3.kick()}};
MN3.cam=function(){const asp=MN3.w/Math.max(1,MN3.h),dist=asp<1.2?23.5:20,pitch=55*Math.PI/180;
  return{eye:[0,Math.sin(pitch)*dist,Math.cos(pitch)*dist+.4],ctr:[0,-.3,.4]}};
MN3.vp=function(){const c=MN3.cam(),asp=MN3.w/Math.max(1,MN3.h);return{vp:M4.mul(M4.persp(36*Math.PI/180,asp,1,80),M4.look(c.eye,c.ctr,[0,1,0])),eye:c.eye}};
MN3.pick=function(nx,ny){ // ray vs pawn spheres; only glowing (legal) pawns can be picked
  const{vp}=MN3.vp(),inv=MN3.inv(vp);if(!inv)return null;
  const unp=(x,y,z)=>{const v=[x,y,z,1],o=[0,0,0,0];for(let r=0;r<4;r++)o[r]=inv[r]*v[0]+inv[4+r]*v[1]+inv[8+r]*v[2]+inv[12+r]*v[3];return[o[0]/o[3],o[1]/o[3],o[2]/o[3]]};
  const a=unp(nx,ny,-1),b=unp(nx,ny,1),d=[b[0]-a[0],b[1]-a[1],b[2]-a[2]],dl=Math.hypot(...d);d[0]/=dl;d[1]/=dl;d[2]/=dl;
  let best=null,bt=1e9;
  for(const k in MN3.pawns){if(!MN3.legal.has(k))continue;const P=MN3.pawns[k],c=[P.x,.55,P.z],o=[a[0]-c[0],a[1]-c[1],a[2]-c[2]];
    const bq=o[0]*d[0]+o[1]*d[1]+o[2]*d[2],cq=o[0]*o[0]+o[1]*o[1]+o[2]*o[2]-.75*.75,disc=bq*bq-cq;
    if(disc>=0){const t=-bq-Math.sqrt(disc);if(t<bt){bt=t;best=P.i}}}
  return best};
MN3.inv=function(m){const inv=new Float32Array(16);
  const a00=m[0],a01=m[1],a02=m[2],a03=m[3],a10=m[4],a11=m[5],a12=m[6],a13=m[7],a20=m[8],a21=m[9],a22=m[10],a23=m[11],a30=m[12],a31=m[13],a32=m[14],a33=m[15];
  const b00=a00*a11-a01*a10,b01=a00*a12-a02*a10,b02=a00*a13-a03*a10,b03=a01*a12-a02*a11,b04=a01*a13-a03*a11,b05=a02*a13-a03*a12,
    b06=a20*a31-a21*a30,b07=a20*a32-a22*a30,b08=a20*a33-a23*a30,b09=a21*a32-a22*a31,b10=a21*a33-a23*a31,b11=a22*a33-a23*a32;
  let det=b00*b11-b01*b10+b02*b09+b03*b08-b04*b07+b05*b06;if(!det)return null;det=1/det;
  inv[0]=(a11*b11-a12*b10+a13*b09)*det;inv[1]=(a02*b10-a01*b11-a03*b09)*det;inv[2]=(a31*b05-a32*b04+a33*b03)*det;inv[3]=(a22*b04-a21*b05-a23*b03)*det;
  inv[4]=(a12*b08-a10*b11-a13*b07)*det;inv[5]=(a00*b11-a02*b08+a03*b07)*det;inv[6]=(a32*b02-a30*b05-a33*b01)*det;inv[7]=(a20*b05-a22*b02+a23*b01)*det;
  inv[8]=(a10*b10-a11*b08+a13*b06)*det;inv[9]=(a01*b08-a00*b10-a03*b06)*det;inv[10]=(a30*b04-a31*b02+a33*b00)*det;inv[11]=(a21*b02-a20*b04-a23*b00)*det;
  inv[12]=(a11*b07-a10*b09-a12*b06)*det;inv[13]=(a00*b09-a01*b07+a02*b06)*det;inv[14]=(a31*b01-a30*b03-a32*b00)*det;inv[15]=(a20*b03-a21*b01+a22*b00)*det;return inv};
MN3.kick=function(){if(!MN3.raf&&MN3.canvas)MN3.raf=requestAnimationFrame(MN3.loop)};
MN3.loop=function(now){
  MN3.raf=0;const cv=MN3.canvas,g=MN3.g;if(!cv||!g||g.lost||!cv.isConnected)return;         // detached: the loop sleeps until the board is shown again
  const dpr=Math.min(2,window.devicePixelRatio||1),w=Math.max(2,Math.round(cv.clientWidth*dpr)),h=Math.max(2,Math.round(cv.clientHeight*dpr));
  if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;MN3.dirty=true}MN3.w=w;MN3.h=h;
  let moving=false;
  for(const k in MN3.pawns){const P=MN3.pawns[k];
    if(P.dur){const t=Math.min(1,(now-P.t0)/P.dur),e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;P.x=P.fx+(P.tx-P.fx)*e;P.z=P.fz+(P.tz-P.fz)*e;P.y=Math.sin(Math.PI*t)*P.hop;
      if(t>=1){P.dur=0;P.y=0;P.x=P.tx;P.z=P.tz}else moving=true}
    if(Math.abs(P.s-P.sT)>.005){P.s+=(P.sT-P.s)*.25;moving=true}else P.s=P.sT}
  const pulse=MN3.legal.size>0;
  if(moving||pulse||MN3.dirty){MN3.draw(now);MN3.dirty=false}
  if(moving||pulse||MN3.dirty)MN3.raf=requestAnimationFrame(MN3.loop)};
MN3.draw=function(now){
  const g=MN3.g,{vp,eye}=MN3.vp(),I=M4.ident();
  g.frame(MN3.w,MN3.h,[0,0,0,0]);
  g.draw(MN3.mBase,I,vp,eye,{color:[.36,.21,.11],shin:30,spec:.2});
  g.draw(MN3.mFrame,I,vp,eye,{color:[.45,.28,.15],shin:40,spec:.3});
  g.draw(MN3.mTop,I,vp,eye,MN3.tex?{tex:MN3.tex,shin:60,spec:.12}:{color:[.95,.96,.98]});
  // soft shadows first (no depth writes), then the pawns
  const gl=g.gl;gl.depthMask(false);
  for(const k in MN3.pawns){const P=MN3.pawns[k];if(P.s<.05)continue;
    g.draw(MN3.mBlob,M4.model(P.x+.12,.03,P.z+.1,0,1.1*P.s*(1-Math.min(.4,P.y*.3))),vp,eye,{blob:true,alpha:.5*(1-Math.min(.6,P.y*.4))})}
  gl.depthMask(true);
  const list=Object.values(MN3.pawns).sort((a,b)=>(a.z*Math.cos(0)-b.z)); // far to near (not needed with depth test, harmless)
  const pl=.5+.5*Math.sin(now/180);
  for(const P of list){if(P.s<.02)continue;const lg=MN3.legal.has(P.u+':'+P.i);
    const lift=lg?Math.abs(Math.sin(now/260))*.18:0;
    g.draw(MN3.mPawn,M4.model(P.x,P.y+lift,P.z,0,P.s*1.25),vp,eye,{color:P.col,shin:36,spec:.4,glow:lg?.25+.35*pl:0})}};
